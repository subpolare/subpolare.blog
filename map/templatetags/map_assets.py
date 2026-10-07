import json
from functools import lru_cache

from django import template
from django.conf import settings
from django.templatetags.static import static

register = template.Library()


@lru_cache(maxsize=1)
def version():
    return json.loads((settings.BASE_DIR / "frontend/static/map/manifest.json").read_text())["version"]


@register.simple_tag
def map_asset(path):
    return static("map/" + path) + "?v=" + version()
