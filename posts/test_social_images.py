from io import BytesIO
from unittest.mock import patch

from django.http import Http404
from django.test import RequestFactory, SimpleTestCase, override_settings
from PIL import Image

from posts.models import Post
from posts.social_images import avatar_badge, post_social_image, render_card, social_image_url
from posts.templatetags.posts import post_social_title


@override_settings(ALLOWED_HOSTS=["testserver", "subpolare.com", "subpolare.ru"])
class SocialImageTests(SimpleTestCase):
    def test_avatar_has_smooth_transparent_edges(self):
        badge = avatar_badge()
        alpha = badge.getchannel("A")
        self.assertEqual(alpha.getpixel((0, 0)), 0)
        self.assertTrue(any(0 < value < 255 for value in alpha.getdata()))
        self.assertEqual(badge.getpixel((badge.width // 2, 1))[:3], (255, 255, 255))

    def test_share_title_combines_title_and_subtitle_without_domain(self):
        post = Post(title="Япония", subtitle="Верь во что угодно, лишь бы ты был счастлив", og_title="Другой OG-заголовок")
        for domain in ("subpolare.ru", "subpolare.com"):
            request = RequestFactory().get("/", HTTP_HOST=domain)
            self.assertEqual(post_social_title({"request": request}, post), "Япония. Верь во что угодно, лишь бы ты был счастлив")

    def test_share_title_handles_missing_fields_and_final_periods(self):
        for title, subtitle, og_title, expected in (
            (" Япония. ", " Подзаголовок... ", "", "Япония. Подзаголовок"),
            ("Япония.", "", "", "Япония"),
            ("", "", "Запасной OG-заголовок.", "Запасной OG-заголовок"),
            ("", "Подзаголовок.", "", "Подзаголовок"),
        ):
            with self.subTest(title=title, subtitle=subtitle):
                post = Post(title=title, subtitle=subtitle, og_title=og_title)
                self.assertEqual(post_social_title({}, post), expected)

    def test_jpeg_dimensions_and_cyrillic_long_titles(self):
        content = render_card("Длинный заголовок на русском " * 8, "Подзаголовок " * 10, "Влад Начатой", "subpolare.ru")
        with Image.open(BytesIO(content)) as image:
            self.assertEqual(image.size, (1200, 800))
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
