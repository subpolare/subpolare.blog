from django import template
from django.template.loader import render_to_string

from common.images import image_attributes, preview_sources

register = template.Library()


@register.simple_tag
def original_image_attributes(url, eager=False):
    return image_attributes(url, eager=eager)


@register.simple_tag
def home_image(url, sizes, eager=False):
    # All homepage cards load immediately; only the top card gets high priority.
    return render_to_string("posts/cards/image.html", {
        "src": url,
        "srcset": preview_sources(url),
        "sizes": sizes,
        "attributes": image_attributes(url, eager=eager, loading="eager"),
    })
