import io
import gzip
import hashlib
import http.client
import json
import socket
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib import admin
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import Http404
from django.middleware.csrf import CsrfViewMiddleware, get_token
from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve, reverse
from django.utils import translation
from PIL import Image

from posts.models import Post
from users.models import User
from .access import safe_post_url
from .admin import MapMarkerAdmin
from .models import MapMarker, validate_color, validate_latitude, validate_longitude
from .previews import MAX_SOURCE_BYTES, PreviewError, _DeadlineSocket, fetch_cover, placeholder, prepare_preview, update_preview
from .views import markers, preview, public_markers


def image_bytes(size=(240, 180), format="PNG"):
    image = Image.new("RGB", size, "#cb6543")
    output = io.BytesIO()
    image.save(output, format=format)
    return output.getvalue()


class MapAssetsTests(SimpleTestCase):
    def test_geodata_has_only_physical_geometry_and_city_fields(self):
        root = Path(__file__).resolve().parent.parent / "frontend/static/map"
        for filename, types, count in (
            ("land.json", ("Polygon", "MultiPolygon"), None),
            ("lakes.json", ("Polygon", "MultiPolygon"), 24),
            ("rivers.json", ("LineString", "MultiLineString"), 13),
        ):
            collection = json.loads((root / filename).read_text())
            self.assertTrue(collection["features"])
            if count is not None:
                self.assertEqual(len(collection["features"]), count)
            for feature in collection["features"]:
                self.assertEqual(feature["properties"], {})
                self.assertIn(feature["geometry"]["type"], types)
        cities = json.loads((root / "cities.json").read_text())
        self.assertEqual(len(cities), 243)
        for city in cities:
            self.assertEqual(set(city), {"coordinates", "ru", "en", "rank", "population"})
            self.assertTrue(city["ru"] and city["en"])
            validate_longitude(city["coordinates"][0])
            validate_latitude(city["coordinates"][1])

    def test_gzip_siblings_manifest_version_and_size_budget_match_source(self):
        root = Path(__file__).resolve().parent.parent / "frontend/static/map"
        manifest = json.loads((root / "manifest.json").read_text())
        digest = hashlib.sha256()
        total = 0
        for path in sorted(root.rglob("*")):
            if path.suffix not in {".js", ".css", ".json"} or path.name == "manifest.json":
                continue
            data = path.read_bytes()
            compressed = path.with_name(path.name + ".gz").read_bytes()
            self.assertEqual(gzip.decompress(compressed), data, path.name)
            digest.update(str(path.relative_to(root)).encode() + b"\0" + data)
            total += len(compressed)
        self.assertEqual(manifest["version"], digest.hexdigest()[:16])
        self.assertEqual(manifest["gzip_bytes"], total)
        self.assertLessEqual(total, 200_000)


class MapValidationTests(SimpleTestCase):
    def test_corrupt_png_checksum_becomes_a_placeholder_instead_of_an_admin_error(self):
        data = bytearray(image_bytes())
        start = data.index(b"IDAT")
        length = int.from_bytes(data[start - 4:start], "big")
        data[start + 4 + length] ^= 1
        point = MapMarker(latitude=0, longitude=0, preview_mode="custom")
        warning = update_preview(point, SimpleUploadedFile("corrupt.png", bytes(data)))
        self.assertIn("заглушка", warning)
        self.assertEqual(point.preview, placeholder())

    def test_coordinates_must_be_finite_and_in_range(self):
        for validator, limit in ((validate_latitude, 90), (validate_longitude, 180)):
            for value in (0, -limit, limit):
                validator(value)
            for value in (float("nan"), float("inf"), float("-inf"), limit + .001, -limit - .001):
                with self.subTest(value=value), self.assertRaises(ValidationError):
                    validator(value)

    def test_color_is_exactly_six_hex_digits(self):
        validate_color("#Ab09fF")
        for value in ("#fff", "#123456\n", "red", "#12345678", "url(x)"):
            with self.assertRaises(ValidationError):
                validate_color(value)

    def test_programmatic_save_validates_before_database(self):
        for fields in ({"latitude": float("nan")}, {"longitude": 181}, {"color": "red"}):
            marker = MapMarker(latitude=0, longitude=0)
            for key, value in fields.items():
                setattr(marker, key, value)
            with self.assertRaises(ValidationError):
                marker.save()

    def test_existing_post_url_semantics_and_unsafe_schemes(self):
        post = Post(type="blog", slug="map", url=None)
        self.assertEqual(safe_post_url(post), "/blog/map/")
        for url in ("https://example.org/a?x=1", "http://example.org/b", "/world/map/"):
            post.url = url
            self.assertEqual(safe_post_url(post), url)
        for url in ("javascript:alert(1)", "data:text/html,x", "//evil.test/x", "/\\evil.test", "https://u:p@example.org", "https://x\n.test", "https://[", " /safe/"):
            post.url = url
            self.assertIsNone(safe_post_url(post), url)

    def test_public_queryset_filters_publication_language_and_membership_not_home_flag(self):
        with translation.override("en"):
            conditions = MapMarker.objects.public().query.where.children
        filters = {condition.lhs.target.name: condition.rhs for condition in conditions}
        self.assertEqual(filters["lang"], "en")
        self.assertTrue(filters["is_enabled"])
        self.assertTrue(filters["is_visible"])
        self.assertFalse(filters["is_members_only"])
        self.assertIn("published_at", filters)
        self.assertNotIn("is_visible_on_home_page", filters)

    def test_json_contract_preserves_untrusted_titles_as_text_and_excludes_bad_links(self):
        post = Post(title='<img src=x onerror="alert(1)">', type="world", slug="ice")
        point = MapMarker(pk=42, post=post, latitude=50, longitude=40, updated_at=datetime(2026, 1, 1))
        with patch("map.views.MapMarker.objects") as manager:
            manager.public.return_value.select_related.return_value.only.return_value = [point]
            response = markers(RequestFactory().get("/map/markers/"))
            data = json.loads(response.content)[0]
            self.assertEqual(set(data), {"id", "latitude", "longitude", "title", "url", "preview", "color"})
            self.assertEqual(data["title"], post.title)
            self.assertTrue(data["preview"].startswith("/map/previews/42/?v="))
            post.url = "javascript:alert(1)"
            self.assertEqual(list(public_markers()), [])

    def test_routes_precede_generic_post_routes_and_public_endpoints_are_get_only(self):
        factory = RequestFactory()
        for name, kwargs in (("map:markers", {}), ("map:preview", {"marker_id": 1})):
            url = reverse(name, kwargs=kwargs)
            match = resolve(url)
            self.assertEqual(match.view_name, name)
            self.assertEqual(match.func(factory.post(url), **match.kwargs).status_code, 405)


class MapPreviewTests(SimpleTestCase):
    def test_response_stream_survives_connection_close_and_obeys_deadline(self):
        # More than the reader buffer, so the body cannot be accidentally served
        # entirely from bytes buffered while parsing the headers.
        body = b"x" * 20000
        sock = Mock()
        stream = io.BytesIO(b"HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: 20000\r\n\r\n" + body)
        sock.makefile.return_value = stream
        wrapped = _DeadlineSocket(sock, 100)
        with patch("map.previews.time.monotonic", return_value=90):
            response = http.client.HTTPResponse(wrapped)
            response.begin()
            self.assertTrue(response.will_close)
            wrapped.close()
            self.assertEqual(response.read(), body)
        sock.makefile.assert_called_once_with("rb", buffering=0)
        self.assertTrue(stream.closed)
        sock = Mock()
        sock.makefile.return_value = io.BytesIO(b"late")
        with patch("map.previews.time.monotonic", return_value=101), self.assertRaises(TimeoutError):
            _DeadlineSocket(sock, 100).makefile("rb").read(1)

    def test_supported_formats_become_small_metadata_free_square_webp(self):
        for format in ("JPEG", "PNG", "WEBP", "GIF"):
            data = prepare_preview(image_bytes(format=format))
            self.assertLessEqual(len(data), 20 * 1024)
            with Image.open(io.BytesIO(data)) as image:
                self.assertEqual(image.size, (128, 128))
                self.assertEqual(image.format, "WEBP")
                self.assertNotIn("exif", image.info)

    def test_invalid_svg_html_oversize_and_huge_dimensions_are_rejected(self):
        for data in (b"", b"<svg/>", b"<html>image</html>", b"x" * (MAX_SOURCE_BYTES + 1), image_bytes(size=(12001, 1))):
            with self.assertRaises(PreviewError):
                prepare_preview(data)

    def test_failure_saves_placeholder_and_warning(self):
        point = MapMarker(post=Post(image="https://i.subpolare.ru/a.jpg"))
        with patch("map.previews.fetch_cover", side_effect=PreviewError("Failed")):
            warning = update_preview(point)
        self.assertIn("заглушка", warning)
        self.assertEqual(point.preview, placeholder())

    def test_custom_image_is_preserved_without_download_and_invalid_upload_falls_back(self):
        point = MapMarker(preview_mode="custom", preview=prepare_preview(image_bytes()))
        old = point.preview
        with patch("map.previews.fetch_cover") as fetch:
            self.assertIsNone(update_preview(point))
            self.assertEqual(point.preview, old)
            warning = update_preview(point, SimpleUploadedFile("fake.png", b"<svg/>"))
        fetch.assert_not_called()
        self.assertTrue(warning)
        self.assertEqual(point.preview, placeholder())

    def test_https_exact_host_and_public_addresses_are_required(self):
        for url in ("http://i.subpolare.ru/a", "https://evil.test/a", "https://i.subpolare.ru.evil.test/a", "https://u:p@i.subpolare.ru/a", "https://i.subpolare.ru:444/a", "file:///etc/passwd", None):
            with patch("map.previews.socket.getaddrinfo") as dns, self.assertRaises(PreviewError):
                fetch_cover(url)
            dns.assert_not_called()
        for address in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "192.168.0.1", "fc00::1", "0.0.0.0"):
            with patch("map.previews.socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]), patch("map.previews.socket.socket") as sock, self.assertRaises(PreviewError):
                fetch_cover("https://i.subpolare.ru/a")
            sock.assert_not_called()

    def test_connection_pins_checked_ip_uses_tls_hostname_and_never_follows_redirects(self):
        address = ("93.184.216.34", 443)
        with patch("map.previews.socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", address)]) as dns, patch("map.previews.socket.socket") as sock, patch("map.previews.ssl.create_default_context") as context, patch("map.previews.http.client.HTTPSConnection") as https:
            response = https.return_value.getresponse.return_value
            response.status = 302
            with self.assertRaises(PreviewError):
                fetch_cover("https://i.subpolare.ru/a")
            dns.assert_called_once()
            sock.return_value.connect.assert_called_once_with(address)
            context.return_value.wrap_socket.assert_called_once_with(sock.return_value, server_hostname="i.subpolare.ru")
            https.return_value.request.assert_called_once()

    def test_download_rejects_oversize_compressed_and_timed_out_responses(self):
        address = ("93.184.216.34", 443)
        with patch("map.previews.socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", address)]), patch("map.previews.socket.socket"), patch("map.previews.ssl.create_default_context"), patch("map.previews.http.client.HTTPSConnection") as https:
            response = https.return_value.getresponse.return_value
            response.status = 200
            for headers in ({"Content-Length": str(MAX_SOURCE_BYTES + 1)}, {"Content-Encoding": "gzip"}):
                response.getheader.side_effect = lambda name, default=None: headers.get(name, default)
                with self.assertRaises(PreviewError):
                    fetch_cover("https://i.subpolare.ru/a")
            response.getheader.side_effect = lambda name, default=None: default
            response.read.return_value = b"x" * (MAX_SOURCE_BYTES + 1)
            with self.assertRaises(PreviewError):
                fetch_cover("https://i.subpolare.ru/a")
            response.read.side_effect = TimeoutError
            with self.assertRaises(PreviewError):
                fetch_cover("https://i.subpolare.ru/a")

    def test_thumbnail_checks_access_before_etag_and_never_processes_images(self):
        request = RequestFactory().get("/map/previews/1/")
        request.user = AnonymousUser()
        point = MapMarker(preview=placeholder())
        with patch("map.views.get_object_or_404", return_value=point), patch("map.previews.fetch_cover") as fetch, patch("map.previews.prepare_preview") as prepare:
            response = preview(request, 1)
            self.assertEqual(response["Content-Type"], "image/webp")
            request = RequestFactory().get("/map/previews/1/", HTTP_IF_NONE_MATCH="W/" + response["ETag"])
            request.user = AnonymousUser()
            self.assertEqual(preview(request, 1).status_code, 304)
        with patch("map.views.get_object_or_404", side_effect=Http404), self.assertRaises(Http404):
            preview(request, 1)
        fetch.assert_not_called()
        prepare.assert_not_called()


class MapAdminAccessTests(SimpleTestCase):
    def setUp(self):
        self.admin = MapMarkerAdmin(MapMarker, admin.site)
        self.factory = RequestFactory()

    def test_all_permissions_and_direct_handlers_require_active_staff_superuser(self):
        users = (AnonymousUser(), User(), User(is_staff=True), User(is_superuser=True), SimpleNamespace(is_authenticated=True, is_active=False, is_staff=True, is_superuser=True))
        for user in users:
            request = self.factory.post("/godmode/map/mapmarker/")
            request.user = user
            for name in ("module", "view", "add", "change", "delete"):
                self.assertFalse(getattr(self.admin, f"has_{name}_permission")(request))
            with self.assertRaises(PermissionDenied):
                self.admin.refresh_previews(request, Mock())
            with self.assertRaises(PermissionDenied):
                self.admin.save_model(request, Mock(), Mock(), False)
            request.method = "GET"
            with self.assertRaises(PermissionDenied):
                self.admin.overview(request)

    def test_admin_posts_have_csrf_protection(self):
        middleware = CsrfViewMiddleware(lambda request: None)
        for name, args in (("changelist", []), ("add", []), ("change", [1]), ("delete", [1])):
            url = reverse("admin:map_mapmarker_" + name, args=args)
            request = self.factory.post(url)
            match = resolve(url)
            self.assertEqual(middleware.process_view(request, match.func, (), match.kwargs).status_code, 403)
            request.META["HTTP_X_CSRFTOKEN"] = get_token(request)
            request.COOKIES["csrftoken"] = request.META["CSRF_COOKIE"]
            self.assertIsNone(middleware.process_view(request, match.func, (), match.kwargs))

    def test_refresh_is_post_only_and_skips_custom_images(self):
        request = self.factory.get("/")
        request.user = User(is_staff=True, is_superuser=True)
        with self.assertRaises(PermissionDenied):
            self.admin.refresh_previews(request, Mock())
        request.method = "POST"
        queryset = Mock()
        queryset.filter.return_value = []
        with patch.object(self.admin, "message_user"):
            self.admin.refresh_previews(request, queryset)
        queryset.filter.assert_called_once_with(preview_mode="article")
