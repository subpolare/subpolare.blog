"""Explicit PostgreSQL suite: manage.py test map.integration_tests --settings=subpolare.integration_test_settings."""
from datetime import timedelta
import io
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation
from PIL import Image

from posts.models import Post
from users.models import User
from .models import MapMarker, MapPlace
from .previews import placeholder
from .tests import image_bytes


class MapPostgreSQLTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_superuser("Owner", "map-owner@example.test", "map-tests")
        cls.staff = User.objects.create_user("Staff", "map-staff@example.test", "map-tests", is_staff=True)
        cls.staff.user_permissions.add(*Permission.objects.filter(content_type__app_label="map"))
        cls.reader = User.objects.create_user("Reader", "map-reader@example.test", "map-tests")

    def setUp(self):
        self.post = self.make_post("first")
        self.point = MapMarker.objects.create(post=self.post, latitude=55.75, longitude=37.62, preview=placeholder())
        self.owner_client = Client(enforce_csrf_checks=True)
        self.owner_client.force_login(self.owner)

    def make_post(self, slug, **kwargs):
        fields = {"slug": slug, "type": "blog", "title": f"Title {slug}", "lang": "ru", "created_at": timezone.now(), "published_at": timezone.now() - timedelta(days=1)}
        fields.update(kwargs)
        return Post.objects.create(**fields)

    def csrf(self, url):
        response = self.owner_client.get(url)
        self.assertEqual(response.status_code, 200)
        return self.owner_client.cookies["csrftoken"].value

    def form_data(self, post=None, **kwargs):
        fields = {"post": str((post or self.post).pk), "latitude": "12.3", "longitude": "-179.9", "color": "#8899AA", "is_enabled": "on", "preview_mode": "article", "_save": "Save"}
        fields.update(kwargs)
        return fields

    def test_database_save_change_unique_article_cascade_and_coordinate_constraints(self):
        self.point.longitude = 180
        self.point.save()
        self.point.refresh_from_db()
        self.assertEqual(self.point.longitude, 180)
        self.assertEqual(bytes(self.point.preview), placeholder())
        with self.assertRaises(IntegrityError), transaction.atomic():
            MapMarker.objects.create(post=self.post, latitude=0, longitude=0)
        for value in (float("nan"), float("inf"), 91):
            with self.assertRaises(IntegrityError), transaction.atomic():
                MapMarker.objects.filter(pk=self.point.pk).update(latitude=value)
        self.post.delete()
        self.assertFalse(MapMarker.objects.filter(pk=self.point.pk).exists())

    @override_settings(ALLOWED_HOSTS=["testserver", "en.subpolare.ru"])
    def test_public_visibility_and_language_are_enforced_in_database(self):
        for slug, flags in (("draft", {"is_visible": False}), ("future", {"published_at": timezone.now() + timedelta(days=1)}), ("members", {"is_members_only": True}), ("english", {"lang": "en"}), ("disabled", {}), ("unsafe", {"url": "javascript:alert(1)"})):
            post = self.make_post(slug, **flags)
            MapMarker.objects.create(post=post, latitude=0, longitude=0, is_enabled=slug != "disabled")
        self.assertFalse(self.post.is_visible_on_home_page)
        with translation.override("ru"):
            data = self.client.get(reverse("map:markers"), HTTP_ACCEPT_LANGUAGE="ru").json()
        self.assertEqual([row["id"] for row in data], [self.point.pk])
        response = self.client.get(reverse("map:markers"), HTTP_HOST="en.subpolare.ru")
        self.assertEqual([row["title"] for row in response.json()], ["Title english"])

    def test_thumbnail_etag_and_revocation_are_checked_on_every_request(self):
        url = reverse("map:preview", args=[self.point.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(url, HTTP_IF_NONE_MATCH=response["ETag"]).status_code, 304)
        for changes in ({"is_visible": False}, {"is_visible": True, "is_members_only": True}, {"is_members_only": False, "published_at": timezone.now() + timedelta(days=1)}):
            Post.objects.filter(pk=self.post.pk).update(**changes)
            self.assertEqual(self.client.get(url, HTTP_IF_NONE_MATCH=response["ETag"]).status_code, 404)
            self.assertEqual(self.owner_client.get(url).status_code, 200)

    def test_private_thumbnails_are_hidden_from_staff_even_with_model_permissions(self):
        self.point.is_enabled = False
        self.point.save()
        url = reverse("map:preview", args=[self.point.pk])
        for user in (None, self.reader, self.staff):
            client = Client()
            if user:
                client.force_login(user)
            self.assertEqual(client.get(url).status_code, 404)

    def test_real_admin_add_change_delete_and_snapshot(self):
        post = self.make_post("new")
        add = reverse("admin:map_mapmarker_add")
        token = self.csrf(add)
        with patch("map.previews.fetch_cover", return_value=placeholder()) as fetch:
            response = self.owner_client.post(add, self.form_data(post=post, csrfmiddlewaretoken=token))
        self.assertEqual(response.status_code, 302)
        fetch.assert_called_once()
        point = MapMarker.objects.get(post=post)
        self.assertEqual(point.latitude, 12.3)
        self.assertTrue(point.preview)
        change = reverse("admin:map_mapmarker_change", args=[point.pk])
        token = self.csrf(change)
        with patch("map.previews.fetch_cover", return_value=placeholder()):
            response = self.owner_client.post(change, self.form_data(post=post, latitude="-90", longitude="180", csrfmiddlewaretoken=token))
        self.assertEqual(response.status_code, 302)
        point.refresh_from_db()
        self.assertEqual((point.latitude, point.longitude), (-90, 180))
        delete = reverse("admin:map_mapmarker_delete", args=[point.pk])
        token = self.csrf(delete)
        self.assertEqual(self.owner_client.post(delete, {"post": "yes", "csrfmiddlewaretoken": token}).status_code, 302)
        self.assertFalse(MapMarker.objects.filter(pk=point.pk).exists())

    def test_duplicate_article_and_invalid_coordinates_are_form_errors(self):
        add = reverse("admin:map_mapmarker_add")
        token = self.csrf(add)
        for data in (self.form_data(), self.form_data(latitude="NaN"), self.form_data(color="red")):
            response = self.owner_client.post(add, dict(data, csrfmiddlewaretoken=token))
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["adminform"].form.errors)
        self.assertEqual(MapMarker.objects.count(), 1)

    def test_custom_upload_content_is_checked_and_only_webp_is_persisted(self):
        change = reverse("admin:map_mapmarker_change", args=[self.point.pk])
        token = self.csrf(change)
        with patch("map.previews.fetch_cover") as fetch:
            response = self.owner_client.post(change, self.form_data(
                preview_mode="custom", csrfmiddlewaretoken=token,
                custom_image=SimpleUploadedFile("cover.png", image_bytes(), content_type="image/png"),
            ))
        self.assertEqual(response.status_code, 302)
        fetch.assert_not_called()
        self.point.refresh_from_db()
        thumbnail = bytes(self.point.preview)
        self.assertLessEqual(len(thumbnail), 20_000)
        with Image.open(io.BytesIO(thumbnail)) as image:
            self.assertEqual((image.format, image.size), ("WEBP", (128, 128)))
        self.post.image = "https://i.subpolare.ru/changed.jpg"
        self.post.save()
        self.point.refresh_from_db()
        self.assertEqual(bytes(self.point.preview), thumbnail)
        response = self.owner_client.post(change, self.form_data(
            preview_mode="custom", csrfmiddlewaretoken=token,
            custom_image=SimpleUploadedFile("fake.png", b"<svg onload='alert(1)'/>", content_type="image/png"),
        ), follow=True)
        self.assertContains(response, "Сохранена нейтральная заглушка")
        self.point.refresh_from_db()
        self.assertEqual(bytes(self.point.preview), placeholder())

    def test_admin_get_only_prefills_fields_without_writing(self):
        response = self.owner_client.get(reverse("admin:map_mapmarker_add"), {"latitude": "50.5", "longitude": "30.5"})
        self.assertContains(response, 'value="50.5"')
        self.assertEqual(MapMarker.objects.count(), 1)
        overview = self.owner_client.get(reverse("admin:map_mapmarker_overview"))
        self.assertEqual(overview.status_code, 200)
        self.assertIn("Опубликована", overview.json()[0]["title"])
        self.assertEqual(self.owner_client.get(reverse("admin:map_mapmarker_overview"), {"q": "missing"}).json(), [])

    def test_anonymous_reader_staff_cannot_use_any_admin_endpoint_or_write(self):
        urls = [reverse("admin:map_mapmarker_" + name, args=args) for name, args in (("changelist", []), ("overview", []), ("add", []), ("change", [self.point.pk]), ("delete", [self.point.pk]), ("history", [self.point.pk]))]
        for user in (None, self.reader, self.staff):
            client = Client()
            if user:
                client.force_login(user)
            for url in urls:
                for method in (client.get, client.post):
                    response = method(url, self.form_data(action="refresh_previews", _selected_action=str(self.point.pk)))
                    self.assertIn(response.status_code, (302, 403, 405), (user, url, response.status_code))
        self.point.refresh_from_db()
        self.assertEqual(self.point.latitude, 55.75)
        self.assertEqual(MapMarker.objects.count(), 1)

    def test_owner_posts_without_csrf_are_rejected_including_bulk_action(self):
        for name, args in (("add", []), ("change", [self.point.pk]), ("delete", [self.point.pk]), ("changelist", [])):
            response = self.owner_client.post(reverse("admin:map_mapmarker_" + name, args=args), self.form_data(action="refresh_previews", _selected_action=str(self.point.pk)))
            self.assertEqual(response.status_code, 403)

    def test_refresh_action_preserves_custom_and_refreshes_article_preview(self):
        custom = MapMarker.objects.create(post=self.make_post("custom"), latitude=0, longitude=0, preview_mode="custom", preview=b"custom-snapshot")
        url = reverse("admin:map_mapmarker_changelist")
        token = self.csrf(url)
        with patch("map.previews.fetch_cover", return_value=placeholder()) as fetch:
            response = self.owner_client.post(url, {"action": "refresh_previews", "_selected_action": [self.point.pk, custom.pk], "csrfmiddlewaretoken": token})
        self.assertEqual(response.status_code, 302)
        fetch.assert_called_once()
        custom.refresh_from_db()
        self.assertEqual(bytes(custom.preview), b"custom-snapshot")

    def test_home_has_safe_fallback_after_about_and_no_eager_map_resources(self):
        self.post.title = '<script>alert("x")</script>'
        self.post.save()
        response = self.client.get("/")
        html = response.content.decode()
        self.assertLess(html.index("index-block-about"), html.index("data-article-map"))
        self.assertLess(html.index("data-article-map"), html.index('<footer'))
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('<script src="/static/map/leaflet', html)
        self.assertNotIn('src="/map/previews/', html)

    def test_yellow_places_seed_and_public_visibility(self):
        self.assertEqual(MapPlace.objects.count(), 29)
        self.assertFalse(MapPlace.objects.filter(name__in=["Белое море", "Тихий океан"]).exists())
        self.assertEqual(MapPlace.objects.get(name="Турция").kind, MapPlace.Kind.COUNTRY)
        self.assertEqual(MapPlace.objects.get(name="Москва").kind, MapPlace.Kind.CITY)
        self.assertEqual(MapPlace.objects.filter(name="Токио").count(), 1)
        self.assertTrue(MapPlace.objects.filter(name="Идзу").exists())
        place = MapPlace.objects.get(name="ББС")
        place.note = '<img src=x onerror="alert(1)">\nЗаметка'
        place.save()
        response = self.client.get(reverse("map:places"))
        self.assertIn("no-store", response["Cache-Control"])
        row = next(row for row in response.json() if row["id"] == place.pk)
        self.assertEqual(row["note"], place.note)
        self.assertEqual(set(row), {"id", "name", "kind", "note", "latitude", "longitude"})
        place.is_enabled = False
        place.save()
        self.assertNotIn(place.pk, [row["id"] for row in self.client.get(reverse("map:places")).json()])
        self.assertEqual(self.client.post(reverse("map:places")).status_code, 405)

    def test_yellow_place_admin_create_edit_delete_and_constraints(self):
        add = reverse("admin:map_mapplace_add")
        token = self.csrf(add)
        fields = {"name": "Новое место", "kind": "city", "latitude": "12.3", "longitude": "45.6", "note": "Короткая заметка", "is_enabled": "on", "csrfmiddlewaretoken": token, "_save": "Save"}
        for invalid in ({"latitude": "NaN"}, {"longitude": "181"}, {"note": "a" * 501}, {"kind": "invalid"}, {"kind": "sea"}, {"kind": "ocean"}):
            response = self.owner_client.post(add, dict(fields, **invalid))
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["adminform"].form.errors)
        self.assertEqual(self.owner_client.post(add, fields).status_code, 302)
        place = MapPlace.objects.get(name="Новое место")
        self.assertEqual(place.kind, MapPlace.Kind.CITY)
        change = reverse("admin:map_mapplace_change", args=[place.pk])
        self.assertEqual(self.owner_client.post(change, dict(fields, note="Изменена", latitude="-90", kind="country")).status_code, 302)
        place.refresh_from_db()
        self.assertEqual((place.note, place.latitude, place.kind), ("Изменена", -90, MapPlace.Kind.COUNTRY))
        for field, value in (("latitude", 91), ("longitude", float("nan")), ("longitude", float("inf"))):
            with self.assertRaises(IntegrityError), transaction.atomic():
                MapPlace.objects.filter(pk=place.pk).update(**{field: value})
        delete = reverse("admin:map_mapplace_delete", args=[place.pk])
        self.assertEqual(self.owner_client.post(delete, {"post": "yes", "csrfmiddlewaretoken": token}).status_code, 302)
        self.assertFalse(MapPlace.objects.filter(pk=place.pk).exists())

    def test_yellow_place_admin_permissions_and_csrf(self):
        place = MapPlace.objects.first()
        for name, args in (("changelist", []), ("add", []), ("change", [place.pk]), ("delete", [place.pk])):
            url = reverse("admin:map_mapplace_" + name, args=args)
            self.assertEqual(self.owner_client.post(url, {}).status_code, 403)
            for user in (None, self.reader, self.staff):
                client = Client()
                if user:
                    client.force_login(user)
                for method in (client.get, client.post):
                    self.assertIn(method(url, {}).status_code, (302, 403))
