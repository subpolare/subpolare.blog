"""Image metadata from Pepic's read-only volume; never fetch images while rendering."""
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import urlsplit

from django.conf import settings
from django.utils.html import format_html_join
from PIL import Image, UnidentifiedImageError


PREVIEW_LENGTHS = (480, 960, 1440)
PREVIEW_VERSION = "1"
IMAGE_NAME = re.compile(r"[a-f0-9]{64}\.(?:jpg|jpeg|png|webp|gif|avif)", re.IGNORECASE)


def pepic_filename(url):
    parsed = urlsplit(url or "")
    origin = urlsplit(settings.PEPIC_MEDIA_ORIGIN)
    if (parsed.scheme, parsed.netloc) != (origin.scheme, origin.netloc):
        return None
    # Preserve originals, including the legacy /full/ spelling. Arbitrary remote
    # URLs and already resized URLs must not become filesystem paths.
    name = parsed.path.removeprefix("/full/").removeprefix("/")
    return name if IMAGE_NAME.fullmatch(name) else None


def storage_path(filename, directory="orig"):
    root = settings.PEPIC_STORAGE_ROOT
    if not root:
        return None
    # Pepic's CanonizeFileName splits the first nine hash characters into three
    # directories. This is its existing production storage layout.
    return Path(root) / directory / filename[:3] / filename[3:6] / filename[6:9] / filename[9:]


@lru_cache(maxsize=4096)
def _read_dimensions(path, modified, size):
    with Image.open(path) as image:
        return image.size


def file_dimensions(path):
    if path is None:
        return None
    try:
        stat = path.stat()
        return _read_dimensions(str(path), stat.st_mtime_ns, stat.st_size)
    except (OSError, ValueError, UnidentifiedImageError):
        return None


def image_dimensions(url):
    name = pepic_filename(url)
    return file_dimensions(storage_path(name)) if name else None


def image_attributes(url, eager=False, *, loading=None):
    attrs = {"loading": loading or ("eager" if eager else "lazy"), "decoding": "async"}
    if eager:
        attrs["fetchpriority"] = "high"
    dimensions = image_dimensions(url)
    if dimensions:
        attrs.update(width=dimensions[0], height=dimensions[1])
    return format_html_join(" ", '{}="{}"', attrs.items())


def preview_sources(url):
    name = pepic_filename(url)
    dimensions = image_dimensions(url)
    if not name or not dimensions:
        return ""
    candidates = {}
    for length in PREVIEW_LENGTHS:
        # Only advertise files that have already been generated. In particular,
        # portrait descriptors are actual pixel widths, not Pepic's long side.
        if length >= max(dimensions):
            continue
        resized = file_dimensions(storage_path(name, f"resize/{length}"))
        if resized and resized[0] < dimensions[0]:
            candidates[resized[0]] = (
                f"{settings.PEPIC_MEDIA_ORIGIN}/{length}/{name}?v={PREVIEW_VERSION}"
            )
    candidates[dimensions[0]] = url
    return ", ".join(f"{src} {width}w" for width, src in sorted(candidates.items()))


class _ArticleImages(HTMLParser):
    """Change img start tags only, leaving author HTML and text byte-for-byte."""
    def __init__(self, html):
        super().__init__(convert_charrefs=False)
        self.html = html
        self.offsets = [0]
        for line in html.split("\n"):
            self.offsets.append(self.offsets[-1] + len(line) + 1)
        self.replacements = []

    def handle_starttag(self, tag, attributes):
        if tag != "img":
            return
        attrs = dict(attributes)
        additions = {}
        if "loading" not in attrs:
            additions["loading"] = "lazy"
        if "decoding" not in attrs:
            additions["decoding"] = "async"
        dimensions = image_dimensions(attrs.get("src"))
        if dimensions and "width" not in attrs and "height" not in attrs:
            additions.update(width=dimensions[0], height=dimensions[1])
        if not additions:
            return
        original = self.get_starttag_text()
        end = "/>" if original.endswith("/>") else ">"
        extra = format_html_join("", ' {}="{}"', additions.items())
        replacement = original[:-len(end)] + str(extra) + end
        line, column = self.getpos()
        start = self.offsets[line - 1] + column
        self.replacements.append((start, start + len(original), replacement))

    handle_startendtag = handle_starttag


def prepare_article_images(html):
    parser = _ArticleImages(html)
    parser.feed(html)
    for start, end, replacement in reversed(parser.replacements):
        html = html[:start] + replacement + html[end:]
    return html
