"""Run explicitly with subpolare.integration_test_settings and disposable PostgreSQL."""
from datetime import timedelta
from unittest.mock import patch

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from posts.models import Post
from users.models import User


class PostPersistenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_superuser(
            "Owner", "post-owner@example.test", "post-tests"
        )
        cls.post = Post.objects.create(
            slug="framework-upgrade",
            type="blog",
            title="Original title",
            text="Original text",
            lang="ru",
            created_at=timezone.now() - timedelta(days=1),
            published_at=timezone.now() - timedelta(days=1),
        )

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.owner)
        self.edit_url = reverse(
            "edit_post", args=[self.post.type, self.post.slug]
        )
        self.assertEqual(self.client.get(self.edit_url).status_code, 200)
        self.csrf = self.client.cookies["csrftoken"].value

    def test_editor_saves_fields_and_renders_fresh_markdown(self):
        Post.objects.filter(pk=self.post.pk).update(html_cache="<p>Old cache</p>")
        response = self.client.post(self.edit_url, {
            "csrfmiddlewaretoken": self.csrf,
            "title": "Updated title",
            "subtitle": "Updated subtitle",
            "image": "https://example.test/cover.jpg",
            "text": "A **fresh** paragraph.",
        })
        self.assertEqual(response.status_code, 302)
        self.post.refresh_from_db()
        self.assertEqual(self.post.title, "Updated title")
        self.assertEqual(self.post.subtitle, "Updated subtitle")
        self.assertEqual(self.post.image, "https://example.test/cover.jpg")
        self.assertEqual(self.post.text, "A **fresh** paragraph.")
        self.assertIsNone(self.post.html_cache)
        self.assertEqual(response["Location"], self.post.get_absolute_url())
        self.assertContains(
            self.client.get(self.post.get_absolute_url()), "<strong>fresh</strong>"
        )

    def test_invalid_editor_submission_keeps_saved_post(self):
        response = self.client.post(self.edit_url, {
            "csrfmiddlewaretoken": self.csrf,
            "title": "Must not be saved",
            "text": "![Ошибка загрузки файла... 1]()",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Дождитесь загрузки изображений")
        self.post.refresh_from_db()
        self.assertEqual(self.post.title, "Original title")
        self.assertEqual(self.post.text, "Original text")

    def test_reading_time_is_saved_on_creation_and_editor_update(self):
        self.post.refresh_from_db()
        self.assertEqual(self.post.reading_time, 5)
        response = self.client.post(self.edit_url, {
            "csrfmiddlewaretoken": self.csrf,
            "title": "Long article",
            "text": "я" * (23 * 1500),
        })
        self.assertEqual(response.status_code, 302)
        self.post.refresh_from_db()
        self.assertEqual(self.post.reading_time, 25)
        with patch("posts.models.calculate_reading_time", side_effect=AssertionError):
            for _ in range(2):
                self.assertContains(
                    self.client.get(self.post.get_absolute_url()), "~25 минут чтения"
                )
        self.post.refresh_from_db()
        self.assertEqual(self.post.reading_time, 25)
        self.assertEqual(self.post.view_count, 2)

    def test_partial_content_updates_persist_reading_time(self):
        self.post.text = "я" * (17 * 1500)
        self.post.save(update_fields=["text"])
        self.post.refresh_from_db()
        self.assertEqual(self.post.reading_time, 15)

        self.post.text = "[я](https://example.test/" + "x" * 10500 + ")"
        self.post.save(update_fields=["text"])
        self.post.refresh_from_db()
        self.assertEqual(self.post.reading_time, 5)
        self.post.is_raw_html = True
        self.post.save(update_fields=["is_raw_html"])
        self.post.refresh_from_db()
        self.assertEqual(self.post.reading_time, 10)

    def test_long_article_gets_reading_time_on_creation(self):
        post = Post.objects.create(
            slug="long-article", type="blog", text="я" * (17 * 1500),
            created_at=timezone.now(), published_at=timezone.now(),
        )
        post.refresh_from_db()
        self.assertEqual(post.reading_time, 15)



class ReadingTimeMigrationTests(TransactionTestCase):
    def test_backfills_existing_posts_without_changing_metadata(self):
        previous = [("posts", "0004_alter_post_slug_alter_post_unique_together")]
        current = [("posts", "0005_post_reading_time")]
        executor = MigrationExecutor(connection)
        executor.migrate(previous)
        try:
            OldPost = executor.loader.project_state(previous).apps.get_model("posts", "Post")
            timestamp = timezone.now() - timedelta(days=30)
            cases = [
                ("markdown", "я" * (11 * 1500), False, 10),
                ("html", "<p>" + "я" * (23 * 1500) + "</p>", True, 25),
                ("empty", None, False, 5),
            ]
            for slug, text, is_raw_html, _ in cases:
                OldPost.objects.create(
                    slug=slug, type="blog", text=text, is_raw_html=is_raw_html,
                    created_at=timestamp, published_at=timestamp, updated_at=timestamp,
                    view_count=42, comment_count=3, html_cache="Old cached HTML",
                )
            executor = MigrationExecutor(connection)
            executor.migrate(current)
            for slug, _, _, expected in cases:
                with self.subTest(slug=slug):
                    post = executor.loader.project_state(current).apps.get_model("posts", "Post").objects.get(slug=slug)
                    self.assertEqual(post.reading_time, expected)
                    self.assertEqual(post.created_at, timestamp)
                    self.assertEqual(post.published_at, timestamp)
                    self.assertEqual(post.updated_at, timestamp)
                    self.assertEqual(post.view_count, 42)
                    self.assertEqual(post.comment_count, 3)
                    self.assertEqual(post.html_cache, "Old cached HTML")
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
