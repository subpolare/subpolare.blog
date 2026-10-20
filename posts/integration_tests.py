"""Run explicitly with subpolare.integration_test_settings and disposable PostgreSQL."""
from datetime import timedelta

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from comments.models import Comment
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

    def test_comment_persists_and_updates_count_with_csrf(self):
        response = self.client.post(reverse("create_comment"), {
            "csrfmiddlewaretoken": self.csrf,
            "post_slug": self.post.slug,
            "text": "A **saved** comment.",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<strong>saved</strong>")
        comment = Comment.objects.get(post=self.post)
        self.assertEqual(comment.author, self.owner)
        self.assertEqual(comment.text, "A **saved** comment.")
        self.post.refresh_from_db()
        self.assertEqual(self.post.comment_count, 1)
