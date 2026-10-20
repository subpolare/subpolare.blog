"""Deploy-time preview preparation and audited HTML-cache refresh."""
import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
import requests

from common.images import (
    PREVIEW_LENGTHS, PREVIEW_VERSION, image_dimensions, pepic_filename,
    storage_path, file_dimensions,
)
from common.markdown.markdown import markdown_text
from posts.models import Post


def original_checksums():
    root = Path(settings.PEPIC_STORAGE_ROOT) / "orig"
    if not settings.PEPIC_STORAGE_ROOT or not root.is_dir():
        raise CommandError("Mount Pepic uploads read-only and set PEPIC_STORAGE_ROOT first.")
    checksums = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            with path.open("rb") as source:
                checksums[str(path.relative_to(root))] = hashlib.file_digest(source, "sha256").hexdigest()
    return checksums


def post_state(post):
    # Exclude view counts: visitors can continue reading during deployment.
    return {
        "text_sha256": hashlib.sha256((post.text or "").encode()).hexdigest(),
        "css": post.css,
        "image": post.image,
        "og_image": post.og_image,
        "created_at": post.created_at.isoformat(),
        "published_at": post.published_at.isoformat(),
        "updated_at": post.updated_at.isoformat(),
        "is_raw_html": post.is_raw_html,
    }


def refresh_cache(posts):
    count = 0
    for post in posts:
        if post.is_raw_html:
            continue
        html = markdown_text(post.text or "")
        if html != post.html_cache:
            # Deliberately bypass Post.save(), which changes updated_at.
            count += Post.objects.filter(pk=post.pk).update(html_cache=html)
    return count


class Command(BaseCommand):
    help = "Warm homepage previews before rollout, then refresh HTML without changing post dates."

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--warm-previews", action="store_true")
        mode.add_argument("--refresh-cache", action="store_true")
        mode.add_argument("--verify", action="store_true")
        parser.add_argument("--audit-file", type=Path, required=True)

    def handle(self, *args, **options):
        audit_file = options["audit_file"]
        if options["warm_previews"]:
            if audit_file.exists():
                raise CommandError("Audit file already exists; use a new filename.")
            posts = list(Post.objects.all())
            audit = {
                "originals": original_checksums(),
                "posts": {str(p.pk): post_state(p) for p in posts},
                "previous_html_cache": {str(p.pk): p.html_cache for p in posts},
            }
            audit_file.parent.mkdir(parents=True, exist_ok=True)
            audit_file.write_text(json.dumps(audit, ensure_ascii=False, indent=2))
            audit_file.chmod(0o600)
            self.warm_previews()
        else:
            audit = json.loads(audit_file.read_text())

        if original_checksums() != audit["originals"]:
            raise CommandError("Original files changed; stop rollout and inspect the audit.")

        with transaction.atomic():
            posts = list(Post.objects.select_for_update().all())
            if {str(p.pk): post_state(p) for p in posts} != audit["posts"]:
                raise CommandError("Post text, images or dates changed; inspect before continuing.")
            if options["refresh_cache"]:
                count = refresh_cache(posts)
                self.stdout.write(f"Refreshed {count} HTML caches; text and dates preserved.")

        self.stdout.write(
            f"Verified {len(audit['originals'])} original checksums and "
            f"{len(audit['posts'])} post records."
        )

    def warm_previews(self):
        urls = {
            post.main_image() for post in
            Post.visible_objects().filter(is_visible_on_home_page=True)
        }
        count = 0
        with requests.Session() as session:
            for url in sorted(u for u in urls if u):
                name = pepic_filename(url)
                dimensions = image_dimensions(url)
                if not name or not dimensions:
                    raise CommandError(f"Cannot read homepage image dimensions: {url}")
                for length in PREVIEW_LENGTHS:
                    if length >= max(dimensions):
                        continue
                    resized_url = (
                        f"{settings.PEPIC_MEDIA_ORIGIN}/{length}/{name}?v={PREVIEW_VERSION}"
                    )
                    with session.get(
                        resized_url, timeout=(10, 60), stream=True, allow_redirects=False,
                    ) as response:
                        if response.status_code != 200:
                            raise CommandError(f"Preview returned {response.status_code}: {resized_url}")
                        for _ in response.iter_content(65536):
                            pass
                    actual = file_dimensions(storage_path(name, f"resize/{length}"))
                    if not actual or max(actual) > max(dimensions):
                        raise CommandError(f"Invalid or missing prepared preview: {resized_url}")
                    count += 1
        self.stdout.write(f"Prepared {count} previews; upload quality settings unchanged.")
