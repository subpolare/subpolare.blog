"""Retry missing cover previews independently of editing and public requests."""
from pathlib import Path
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, close_old_connections
import requests

from common.image_previews import prepare_previews, PreviewPreparationError
from posts.models import Post


class Command(BaseCommand):
    help = "Automatically prepare homepage covers, including drafts and scheduled posts."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--interval", type=int, default=3600)

    def handle(self, *args, **options):
        if options["interval"] < 1:
            raise CommandError("--interval must be at least one second.")
        if not settings.PEPIC_STORAGE_ROOT or not (Path(settings.PEPIC_STORAGE_ROOT) / "orig").is_dir():
            raise CommandError("Mount Pepic uploads read-only and set PEPIC_STORAGE_ROOT first.")

        if not options["once"]:
            self.stdout.write(f"Preparing covers now, then every {options['interval']} seconds.")
        with requests.Session() as session:
            while True:
                close_old_connections()
                try:
                    failed = self.prepare_covers(session)
                except DatabaseError as error:
                    self.stderr.write(f"Cannot read covers; will retry: {error}")
                    failed = True
                finally:
                    close_old_connections()
                if options["once"]:
                    if failed:
                        raise CommandError("Some previews could not be prepared.")
                    return
                # Files are the durable completion record. Restarting the worker
                # or a partial failure never loses pending covers.
                time.sleep(options["interval"])

    def prepare_covers(self, session):
        # No publication-date, visibility or language filter: prepare drafts
        # before publication, and notice cover changes even via bulk updates.
        posts = Post.objects.filter(is_visible_on_home_page=True).only("image", "og_image")
        urls = {post.main_image() for post in posts} - {None, ""}
        prepared = failed = 0
        for url in sorted(urls):
            try:
                prepared += prepare_previews(url, session)
            except (PreviewPreparationError, requests.RequestException, OSError) as error:
                failed += 1
                self.stderr.write(f"Cover previews will be retried: {error}")
        self.stdout.write(f"Checked {len(urls)} covers; prepared {prepared} previews; failed {failed}.")
        return bool(failed)
