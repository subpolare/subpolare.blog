from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, render
from django.utils.translation import get_language
from django.conf import settings
from django.http import HttpResponse

from clickers.models import Clicker
from posts.models import Post
from utils.request import parse_ip_address


def click_block(request, post_slug, block):
    if settings.SITE_REGION == "com":
        return HttpResponse("Реакции временно недоступны", status=503)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    post = get_object_or_404(Post, slug=post_slug, lang=get_language())

    clicker, is_created = Clicker.objects.get_or_create(
        post=post,
        block=block,
        ipaddress=parse_ip_address(request),
        defaults=dict(
            useragent=request.META.get("HTTP_USER_AGENT", ""),
        )
    )

    if is_created:
        total_clicks = Clicker.objects.filter(post=post, block=block).count()
    else:
        total_clicks = "x"

    return render(request, "clickers/clicker.html", {
        "post": post,
        "text": clicker.block or "",
        "block": clicker.block,
        "votes": total_clicks,
        "is_voted": True,
    })
