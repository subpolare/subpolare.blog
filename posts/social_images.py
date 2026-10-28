"""Standalone share cards. Never alter covers, page content, or stored OG fields."""
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import json

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_safe
from PIL import Image, ImageDraw, ImageFont, ImageOps

from common.images import pepic_filename, storage_path
from posts.models import Post

VERSION = "1"
SIZE = (1200, 630)


def card_fields(post):
    return (post.title or post.og_title or "", post.subtitle or "", post.author or "", post.main_image() or "")


def social_image_url(request, post):
    version = sha256(json.dumps((VERSION, *card_fields(post)), ensure_ascii=False).encode()).hexdigest()[:16]
    path = reverse("post_social_image", kwargs={"post_type": post.type, "post_slug": post.slug})
    return request.build_absolute_uri(f"{path}?v={version}")


def font(size, weight="Medium"):
    return ImageFont.truetype(str(settings.BASE_DIR / f"frontend/static/fonts/raleway/Raleway-{weight}.ttf"), size)


def wrap(text, face, width):
    lines = []
    current = ""
    for word in text.split():
        for char in ((" " if current else "") + word):
            if face.getlength(current + char) > width and current:
                # Prefer a word boundary, splitting individual long words only when necessary.
                if " " in current:
                    before, after = current.rsplit(" ", 1)
                    lines.append(before)
                    current = after + char
                else:
                    lines.append(current)
                    current = char.lstrip()
            else:
                current += char
    if current.strip():
        lines.append(current.strip())
    return lines


def render_card(title, subtitle, author, domain, cover=None):
    canvas = Image.new("RGB", SIZE, "#333333")
    if cover:
        with Image.open(cover) as source:
            canvas = ImageOps.fit(ImageOps.exif_transpose(source).convert("RGB"), SIZE, method=Image.Resampling.LANCZOS)
    # Shade only the identity row; preserve the photograph under the title strips.
    shade = Image.new("RGBA", SIZE)
    draw = ImageDraw.Draw(shade)
    for y in range(180):
        draw.line((0, y, 1200, y), fill=(0, 0, 0, round(125 * (1 - y / 180) ** 2)))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), shade)
    draw = ImageDraw.Draw(canvas)
    icon_path = settings.BASE_DIR / "frontend/static/images/logo_128.png"
    with Image.open(icon_path) as source:
        icon = ImageOps.fit(source.convert("RGBA"), (48, 48))
    mask = Image.new("L", (48, 48))
    ImageDraw.Draw(mask).ellipse((0, 0, 47, 47), fill=255)
    canvas.paste(icon, (48, 38), mask)
    label = font(25, "SemiBold")
    draw.text((110, 62), author, font=label, fill="white", anchor="lm")
    draw.text((1152, 62), domain, font=label, fill="white", anchor="rm")
    for size in range(62, 17, -1):
        title_font, subtitle_font = font(size), font(round(size * .61), "Regular")
        titles = wrap(title, title_font, 1056)
        subtitles = wrap(subtitle, subtitle_font, 1056)
        title_step, subtitle_step = round(size * 1.28), round(size * .84)
        height = len(titles) * title_step + len(subtitles) * subtitle_step + (18 if subtitles else 0)
        if height <= 410:
            break
    y = 582 - height
    for lines, face, step in ((titles, title_font, title_step), (subtitles, subtitle_font, subtitle_step)):
        for line in lines:
            width = draw.textlength(line, font=face)
            draw.rectangle((600 - width / 2 - 16, y, 600 + width / 2 + 16, y + step), fill="white")
            draw.text((600, y + step / 2), line, font=face, fill="#333333", anchor="mm")
            y += step
        y += 18
    output = BytesIO()
    canvas.convert("RGB").save(output, "JPEG", quality=92, optimize=True)
    return output.getvalue()


@lru_cache(maxsize=128)
def cached_card(fields, domain, path, modified):
    return render_card(*fields[:3], domain, path)


@require_safe
def post_social_image(request, post_type, post_slug):
    post = get_object_or_404(Post.visible_objects(), type=post_type, slug=post_slug)
    fields = card_fields(post)
    name = pepic_filename(fields[3])
    path = storage_path(name) if name else None
    try:
        modified = path.stat().st_mtime_ns if path else None
    except OSError:
        path, modified = None, None
    domain = "subpolare.com" if request.get_host().split(":")[0] in ("subpolare.com", "www.subpolare.com") else "subpolare.ru"
    content = cached_card(fields, domain, path, modified)
    response = HttpResponse(content, content_type="image/jpeg")
    response["Cache-Control"] = "public, max-age=3600"
    response["X-Content-Type-Options"] = "nosniff"
    return response
