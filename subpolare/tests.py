from unittest.mock import Mock, patch

from bs4 import BeautifulSoup
from django.contrib import admin
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve, reverse

from users.models import User


class AdminNavigationTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/godmode/")
        self.request.user = User(is_staff=True, is_superuser=True)

    def test_dashboard_and_sidebar_only_list_map_and_posts(self):
        apps = admin.site.get_app_list(self.request)
        self.assertEqual({app["app_label"] for app in apps}, {"map", "posts"})
        log = Mock()
        log.filter.return_value = []
        with patch.object(admin.site, "get_log_entries", return_value=log):
            response = admin.site.index(self.request)
            response.render()
        for html in (
            response.content.decode(),
            render_to_string("admin/nav_sidebar.html", admin.site.each_context(self.request)),
        ):
            soup = BeautifulSoup(html, "html.parser")
            app_classes = {
                name for element in soup.select(".module") for name in element.get("class", [])
                if name.startswith("app-")
            }
            self.assertEqual(app_classes, {"app-map", "app-posts"})

    def test_hidden_models_stay_registered_and_direct_urls_resolve(self):
        self.assertTrue(admin.site.is_registered(User))
        for model in admin.site._registry:
            opts = model._meta
            url = reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist")
            self.assertEqual(resolve(url).namespace, "admin")
        apps = admin.site.get_app_list(self.request, "users")
        self.assertEqual([app["app_label"] for app in apps], ["users"])

    def test_navigation_respects_existing_permissions(self):
        self.request.user = User(is_staff=True)
        with patch.object(self.request.user, "has_module_perms", return_value=False):
            self.assertEqual(admin.site.get_app_list(self.request), [])


class RetiredSectionsTests(SimpleTestCase):
    def test_removed_post_types_are_not_public_routes(self):
        for kind in ("inside", "365", "gallery"):
            with self.subTest(kind=kind):
                self.assertEqual(self.client.get(f"/{kind}/").status_code, 404)

    def test_subscribe_stays_available_without_inside_app(self):
        response = self.client.get("/subscribe/")
        self.assertContains(response, "https://telegram.me/subpolare_blog")

    def test_notes_and_donate_template_are_retained(self):
        from subpolare.posts import POST_TYPES
        self.assertIn("notes", POST_TYPES)
        self.assertIn("Поддержать автора", render_to_string("donate.html"))
