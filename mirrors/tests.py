import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, Mock

from django.contrib.auth.models import AnonymousUser
from django.core import signing
from django.http import HttpResponse
from django.test import SimpleTestCase, RequestFactory, override_settings

from mirrors.middleware import MirrorMiddleware


@override_settings(ALLOWED_HOSTS=["subpolare.ru", "subpolare.com"], GEO_REDIRECT_ENABLED=True,
                   MIRROR_SIGNING_KEY="test-hop-key", SITE_REGION="ru")
class RoutingTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.app = Mock(return_value=HttpResponse("article"))
        self.middleware = MirrorMiddleware(self.app)

    def request(self, path="/blog/article/?page=2&tag=a&tag=b", host="subpolare.ru", method="get"):
        request = getattr(self.factory, method)(path, HTTP_HOST=host, HTTP_X_REAL_IP="8.8.8.8", secure=True)
        request.user = AnonymousUser()
        return request

    def route(self, request, country="US", available=True):
        with patch("mirrors.geo.country", return_value=country), patch("mirrors.geo.target_available", return_value=available), patch("mirrors.geo.verified_crawler", return_value=False):
            return self.middleware(request)

    def test_redirect_preserves_resource_and_repeated_query_values(self):
        response = self.route(self.request())
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("https://subpolare.com/blog/article/?page=2&tag=a&tag=b&"))
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.app.assert_not_called()

    def test_russia_returns_to_ru(self):
        self.assertTrue(self.route(self.request(host="subpolare.com"), country="RU")["Location"].startswith("https://subpolare.ru/"))

    def test_boosted_navigation_uses_full_page_redirect(self):
        request = self.request()
        request.META["HTTP_HX_REQUEST"] = "true"
        response = self.route(request)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["HX-Redirect"].startswith("https://subpolare.com/blog/article/"))

    def test_redirects_keep_encoded_resource_names(self):
        from mirrors.middleware import redirect_to
        for path in ("/blog/a%23b/", "/blog/a%3Fb/", "/blog/a%2523b/",
                     "/blog/a%5Cb/", "/blog/a%0Ab/", "/blog/%D1%82%D0%B5%D1%81%D1%82/"):
            for boosted in (False, True):
                request = self.request(path + "?tag=a&tag=b")
                if boosted:
                    request.META["HTTP_HX_REQUEST"] = "true"
                response = redirect_to(request, "com")
                header = "HX-Redirect" if boosted else "Location"
                self.assertEqual(response[header], "https://subpolare.com" + path + "?tag=a&tag=b")

    def test_unknown_country_or_unavailable_target_serves_current_site(self):
        for country, available in ((None, True), ("US", False)):
            self.assertEqual(self.route(self.request(), country, available).status_code, 200)

    def test_post_admin_api_preview_and_assets_never_geo_redirect(self):
        for path in ("/godmode/", "/editor/upload/", "/clickers/blocks/x/y/", "/map/markers/", "/map/places/", "/map/markers/?preview=1", "/static/a.css", "/_mirror/health", "/robots.txt", "/sitemap.xml", "/blog/x/edit/", "/blog/x/?preview=1"):
            self.assertEqual(self.route(self.request(path)).status_code, 200, path)
        self.assertEqual(self.route(self.request(method="post")).status_code, 200)

    def test_manual_choice_is_persisted_on_destination_and_preserves_query(self):
        response = self.route(self.request("/blog/x/?page=2&mirror=ru"))
        self.assertEqual(response["Location"], "https://subpolare.ru/blog/x/?page=2")
        self.assertEqual(response.cookies["mirror"].value, "ru")
        request = self.request()
        request.COOKIES["mirror"] = "ru"
        self.assertEqual(self.route(request).status_code, 200)

    def test_invalid_choice_cannot_redirect_to_external_host(self):
        response = self.route(self.request("/blog/x/?mirror=https://evil.test"), country=None)
        self.assertEqual(response.status_code, 200)

    def test_manual_switch_updates_departure_domain_cookie_too(self):
        request = self.request("/blog/x/?mirror=ru", host="subpolare.com")
        request.COOKIES["mirror"] = "com"
        response = self.route(request)
        self.assertEqual(response.cookies["mirror"].value, "ru")
        self.assertEqual(response["Location"], "https://subpolare.ru/blog/x/?mirror=ru")

    def test_signed_arrival_prevents_reverse_redirect(self):
        token = signing.dumps({"region": "com", "path": "/blog/x/"}, key="test-hop-key", salt="mirror-hop")
        response = self.route(self.request("/blog/x/?_mirror_hop=" + token, host="subpolare.com"), country="RU")
        self.assertEqual(response["Location"], "https://subpolare.com/blog/x/")
        request = self.request("/blog/x/", host="subpolare.com")
        request.COOKIES["mirror_arrived"] = response.cookies["mirror_arrived"].value
        self.assertEqual(self.route(request, country="RU").status_code, 200)

    def test_forged_arrival_does_not_bypass_routing(self):
        response = self.route(self.request("/blog/x/?_mirror_hop=forged"))
        self.assertTrue(response["Location"].startswith("https://subpolare.com/"))

    def test_verified_crawler_stays_on_requested_url(self):
        with patch("mirrors.geo.country", return_value="US"), patch("mirrors.geo.target_available", return_value=True), patch("mirrors.geo.verified_crawler", return_value=True):
            self.assertEqual(self.middleware(self.request()).status_code, 200)

    @override_settings(SITE_REGION="com")
    def test_foreign_instance_rejects_edits_and_rewrites_owned_media(self):
        self.assertEqual(self.route(self.request("/editor/upload/", host="subpolare.com", method="post")).status_code, 403)
        self.app.return_value = HttpResponse('<img src="https://media.subpolare.ru/a.jpg"><img src="https://other.test/a.jpg">')
        response = self.route(self.request(host="subpolare.com"))
        self.assertIn(b"https://subpolare.com/media/a.jpg", response.content)
        self.assertIn(b"https://other.test/a.jpg", response.content)


class GeoFallbackTests(SimpleTestCase):
    def test_ip_fallback_supports_asgi_requests_without_environ(self):
        from types import SimpleNamespace
        from utils.request import parse_ip_address
        request = SimpleNamespace(META={"REMOTE_ADDR": "203.0.113.12"})
        self.assertEqual(parse_ip_address(request), "203.0.113.12")

    def test_missing_database_or_health_state_fails_open(self):
        from mirrors import geo
        with TemporaryDirectory() as directory, override_settings(MIRROR_RUNTIME=directory):
            self.assertIsNone(geo.country("8.8.8.8"))
            self.assertFalse(geo.target_available())
            Path(directory, "peer.json").write_text(json.dumps({"healthy": True, "checked_at": 0}))
            self.assertFalse(geo.target_available())


@override_settings(SITE_REGION="com")
class MirrorHealthTests(SimpleTestCase):
    def test_readable_mirror_is_not_fresh_when_replication_or_media_stops(self):
        from mirrors.views import health
        with TemporaryDirectory() as directory, override_settings(PEPIC_STORAGE_ROOT=directory):
            marker = Path(directory, ".mirror-synced")
            for replica, timestamp, expected in ((True, 999, 200), (False, 999, 503),
                                                  (True, 1, 503), (True, 1001, 503)):
                marker.write_text(str(timestamp))
                cursor = Mock()
                cursor.fetchone.side_effect = [(True,), (replica,)]
                with patch("mirrors.views.connection") as connection, patch("mirrors.views.time.time", return_value=1000):
                    connection.cursor.return_value.__enter__.return_value = cursor
                    response = health(RequestFactory().get("/_mirror/health"))
                self.assertEqual(response.status_code, expected)
                self.assertTrue(json.loads(response.content)["readable"])
                self.assertEqual(response["Cache-Control"], "no-store")

    def test_missing_or_invalid_media_marker_is_not_fresh(self):
        from mirrors.views import media_fresh
        with TemporaryDirectory() as directory, override_settings(PEPIC_STORAGE_ROOT=directory):
            self.assertFalse(media_fresh())
            Path(directory, ".mirror-synced").write_text("invalid")
            self.assertFalse(media_fresh())


class MediaReceiverTests(SimpleTestCase):
    def test_only_fixed_data_roots_are_delegated_to_rrsync(self):
        import runpy
        receiver = runpy.run_path(str(Path(__file__).resolve().parents[1] / "etc/ssh/mirror-media-receive.py"))
        with patch("os.path.realpath", side_effect=lambda value: value), patch("os.path.isdir", return_value=True), patch("os.execve") as execute:
            for selector, root in receiver["ROOTS"].items():
                receiver["receive"](selector + " --server -rt . ./")
                command, arguments, env = execute.call_args.args
                self.assertEqual(command, "/usr/bin/rrsync")
                self.assertEqual(arguments, ["rrsync", "-wo", "-no-del", "-munge", root])
                self.assertEqual(env["SSH_ORIGINAL_COMMAND"], "rsync --server -rt . ./")
            for command in ("", "rsync --server -rt . ./", "../.env --server -rt . ./",
                            "uploads;whoami --server -rt . ./", "uploads cat .env"):
                with self.assertRaises(ValueError):
                    receiver["receive"](command)

    def test_symlinked_data_roots_are_rejected(self):
        import runpy
        receiver = runpy.run_path(str(Path(__file__).resolve().parents[1] / "etc/ssh/mirror-media-receive.py"))
        with patch("os.path.realpath", return_value="/srv/pepic"), self.assertRaises(ValueError):
            receiver["receive"]("uploads --server -rt . ./")


class MirrorMaintenanceTests(SimpleTestCase):
    def test_provider_refresh_does_not_block_health_and_once_waits_for_completion(self):
        from threading import Event
        from mirrors.management.commands.mirror_maintenance import Command
        probe = Event()
        refreshed = []

        def slow_refresh(*args):
            refreshed.append(probe.wait(timeout=2))

        def health_response(*args, **kwargs):
            probe.set()
            return Mock(status_code=200, json=lambda: {"ready": True})

        with TemporaryDirectory() as directory, override_settings(MIRROR_RUNTIME=directory), \
                patch("mirrors.management.commands.mirror_maintenance.refresh_databases", side_effect=slow_refresh), \
                patch("mirrors.management.commands.mirror_maintenance.requests.get", side_effect=health_response):
            Command(stderr=Mock()).handle(once=True)
            self.assertEqual(refreshed, [True])
            self.assertTrue(json.loads(Path(directory, "peer.json").read_text())["healthy"])
            self.assertTrue(json.loads(Path(directory, "local.json").read_text())["ready"])
