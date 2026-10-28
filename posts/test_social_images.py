from io import BytesIO
from unittest.mock import patch

from django.http import Http404
from django.test import RequestFactory, SimpleTestCase, override_settings
from PIL import Image

from posts.models import Post
from posts.social_images import post_social_image, render_card, social_image_url


@override_settings(ALLOWED_HOSTS=["testserver", "subpolare.com", "subpolare.ru"])
class SocialImageTests(SimpleTestCase):
    def test_jpeg_dimensions_and_cyrillic_long_titles(self):
        content = render_card("Длинный заголовок на русском " * 8, "Подзаголовок " * 10, "Влад Начатой", "subpolare.ru")
        with Image.open(BytesIO(content)) as image:
            self.assertEqual(image.size, (1200, 630))
            self.assertEqual(image.format, "JPEG")

    def test_url_tracks_domain_and_content_without_changing_fields(self):
        post = Post(type="world", slug="japan", title="Япония", og_image="https://example.org/original.jpg")
        request = RequestFactory().get("/", secure=True, HTTP_HOST="subpolare.com")
        first = social_image_url(request, post)
        self.assertTrue(first.startswith("https://subpolare.com/_social/world/japan.jpg?v="))
        post.subtitle = "Новый подзаголовок"
        self.assertNotEqual(first, social_image_url(request, post))
        self.assertEqual(post.og_image, "https://example.org/original.jpg")

    @patch("posts.social_images.get_object_or_404", side_effect=Http404)
    @patch("posts.social_images.Post.visible_objects")
    def test_only_public_posts_are_accessible(self, visible, lookup):
        with self.assertRaises(Http404):
            post_social_image(RequestFactory().get("/"), "blog", "draft")
        lookup.assert_called_once_with(visible.return_value, type="blog", slug="draft")

    @patch("posts.social_images.cached_card", return_value=b"jpeg")
    @patch("posts.social_images.get_object_or_404")
    @patch("posts.social_images.Post.visible_objects")
    def test_domain_is_passed_to_image_and_no_remote_cover_is_fetched(self, visible, lookup, render):
        lookup.return_value = Post(title="Статья", image="https://example.org/image.jpg")
        response = post_social_image(RequestFactory().get("/", HTTP_HOST="subpolare.com"), "blog", "post")
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertEqual(render.call_args.args[1:], ("subpolare.com", None, None))
