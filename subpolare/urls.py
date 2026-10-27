from django.conf import settings
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import path, include
from django.views.generic import RedirectView

from clickers.views import click_block
from subpolare.pages import donate, subscribe
from posts.sitemaps import sitemaps
from posts.views import index, show_post, list_posts, edit_post
from posts.editor import preview_post, upload_post_image
from rss.views import full_feed
from users.views import robots
from users.views import yandex_verification
from mirrors.views import health

urlpatterns = [
    path("_mirror/health", health, name="mirror_health"),
    path("", index, name="index"),

    path(r"godmode/", admin.site.urls),

    # path(r"donate/", donate, name="donate"),
    path(r"subscribe/", subscribe, name="subscribe"),

    path(r"rss/", full_feed, name="rss.full"),
    path(r"rss/public/", full_feed, name="rss.public"),
    path(r"rss/private/", full_feed, name="rss.private"),
    path(r"rss/blog/", full_feed, name="rss.blog"),  # legacy

    path(r"clickers/blocks/<str:post_slug>/<str:block>/", click_block, name="click_block"),


    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="sitemap"),
    path("robots.txt", robots, name="robots"),
    path("yandex_5a8ac3fe600ec2e1.html", yandex_verification, name="yandex_verification"),

    path("editor/upload/", upload_post_image, name="upload_post_image"),
    path("map/", include("map.urls")),
    path("<str:post_type>/<str:post_slug>/edit/preview/", preview_post, name="preview_post"),
    path(r"<str:post_type>/<str:post_slug>/", show_post, name="show_post"),
    path(r"<str:post_type>/<str:post_slug>/index.html", show_post, name="show_post_legacy"),  # legacy fallback
    path(r"<str:post_type>/<str:post_slug>/edit/", edit_post, name="edit_post"),
    path(
        r"<str:post_type>/<str:post_slug>/<str:block>/",
        RedirectView.as_view(url="/%(post_type)s/%(post_slug)s#%(block)s", permanent=True),
        name="show_post_block"
    ),
    path(r"<str:post_type>/", list_posts, name="list_posts"),
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
