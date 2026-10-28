import re

from django import template
from django.conf import settings
from django.template import loader
from django.utils.safestring import mark_safe

from common.markdown.markdown import markdown_text
from common.markdown.headings import semantic_headings
from common.images import prepare_article_images

register = template.Library()
clicker_template = loader.get_template("clickers/clicker.html")


@register.simple_tag(takes_context=True)
def show_post(context, post):
    if post.is_raw_html:
        html = prepare_article_images(post.text or post.html_cache or "")
    else:
        if not post.html_cache or settings.DEBUG:
            new_html = markdown_text(post.text)
            if new_html != post.html_cache:
                # to not flood into history
                post.html_cache = new_html
                if settings.SITE_REGION != "com":
                    post.save(flush_cache=False, update_fields=["html_cache"])
        html = semantic_headings(post.html_cache or "")

    return mark_safe(render_post_blocks(context, html))

def render_post_blocks(context, html):
    """Expand legacy blocks without reading or writing the post/cache."""
    # Old markers should stay invisible when comments are retired.
    html = re.sub(r"\[commentable (.+?)\]", "", html)
    return re.sub(r"\[clicker (.+?)\]", lambda match: clicker(context, match.group(1), match.group(1)), html)


def clicker(context, block, text=None):
    clicker = context["clickers"].get(block) or {}

    return clicker_template.render({
        **context.flatten(),
        "text": text or "",
        "block": block,
        "votes": clicker.get("total") or 0,
        "is_voted": block in context["user_votes"],
    })


@register.simple_tag(takes_context=True)
def post_social_image_url(context, post):
    from posts.social_images import social_image_url
    return social_image_url(context["request"], post)
