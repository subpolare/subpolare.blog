from django.conf import settings
from django.http import Http404
from django.views.decorators.cache import cache_page

from rss.feeds import FullFeed


_cached_feed = cache_page(60 * 60)(FullFeed())


def full_feed(request, *args, **kwargs):
    # Check before the cache so disabling RSS also hides a previously cached feed.
    if not settings.RSS_ENABLED:
        raise Http404()
    return _cached_feed(request, *args, **kwargs)
