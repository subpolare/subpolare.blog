from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from rss.feeds import FullFeed


class FeedAvailabilityTests(SimpleTestCase):
    paths = ("/rss/", "/rss/public/", "/rss/private/", "/rss/blog/")

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    @override_settings(RSS_ENABLED=False)
    def test_disabled_feeds_are_unavailable_and_not_advertised(self):
        with patch.object(FullFeed, "items") as items:
            for path in self.paths:
                self.assertEqual(self.client.get(path).status_code, 404)
            items.assert_not_called()
        self.assertNotContains(self.client.get("/subscribe/"), 'type="application/rss+xml"')

    @override_settings(RSS_ENABLED=True)
    def test_enabled_feed_keeps_aliases_and_uses_site_name(self):
        with patch.object(FullFeed, "items", return_value=[]):
            for path in self.paths:
                response = self.client.get(path)
                self.assertContains(response, "<title>subpolare.ru</title>")
                self.assertNotContains(response, "Вастрик")
        self.assertContains(self.client.get("/subscribe/"), 'type="application/rss+xml"')
        self.assertEqual(FullFeed().author_name(), "subpolare.ru")

    def test_disabling_feed_takes_precedence_over_a_warm_cache(self):
        with override_settings(RSS_ENABLED=True), patch.object(FullFeed, "items", return_value=[]):
            self.assertEqual(self.client.get("/rss/").status_code, 200)
        with override_settings(RSS_ENABLED=False):
            self.assertEqual(self.client.get("/rss/").status_code, 404)
