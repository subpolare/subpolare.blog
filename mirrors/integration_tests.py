from datetime import datetime
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.template import Context
from django.http import HttpResponse

from mirrors.models import LocalPostViews
from posts.models import Post
from posts.templatetags.posts import show_post


class MirrorPersistenceTests(TestCase):
    def setUp(self):
        self.post = Post.objects.create(type="blog", slug="mirror-test", title="Mirror", text="Text",
            author="test", created_at=datetime.utcnow(), view_count=27)

    def test_local_counter_is_not_overwritten_by_content_update(self):
        LocalPostViews.objects.create(post_id=self.post.pk, count=12)
        Post.objects.filter(pk=self.post.pk).update(title="Changed", view_count=99)
        self.post.refresh_from_db()
        self.assertEqual(self.post.local_view_count, 12)

    def test_read_increments_local_counter_without_updating_replicated_post(self):
        with patch("posts.views.render_post", return_value=HttpResponse("ok")):
            self.client.get(self.post.get_absolute_url())
        self.post.refresh_from_db()
        self.assertEqual(self.post.view_count, 27)
        self.assertEqual(self.post.local_view_count, 1)

    @override_settings(SITE_REGION="com")
    def test_rendering_on_mirror_does_not_write_content_cache(self):
        show_post(Context({"clickers": {}, "user_votes": set()}), self.post)
        self.post.refresh_from_db()
        self.assertIsNone(self.post.html_cache)

    @override_settings(SITE_REGION="com")
    def test_direct_reaction_write_to_mirror_is_rejected(self):
        response = self.client.post("/clickers/blocks/mirror-test/hello/")
        self.assertEqual(response.status_code, 503)
