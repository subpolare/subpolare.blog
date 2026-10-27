from datetime import datetime
import hashlib
from tempfile import TemporaryDirectory
from unittest.mock import patch

from bs4 import BeautifulSoup
from django.template import Context
from django.template.loader import render_to_string
from django.test import SimpleTestCase, override_settings
from PIL import Image

from common.images import (
    image_dimensions, pepic_filename, prepare_article_images,
    preview_sources, storage_path,
)
from common.markdown.markdown import markdown_text
from posts.management.commands.prepare_image_delivery import refresh_cache
from posts.models import Post
from posts.templatetags.posts import show_post


class ImageDeliveryTests(SimpleTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings_override = override_settings(
            PEPIC_STORAGE_ROOT=self.temp.name,
            PEPIC_MEDIA_ORIGIN="https://media.example.test",
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.name = "a" * 64 + ".jpg"
        self.url = "https://media.example.test/" + self.name
        self.write_image("orig", (900, 1800))

    def write_image(self, directory, dimensions):
        path = storage_path(self.name, directory)
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", dimensions, color=(40, 80, 120)).save(path, quality=95)
        return path

    def test_article_uses_identical_original_bytes_and_reserves_portrait_space(self):
        path = storage_path(self.name)
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        with patch("requests.get") as get:
            html = markdown_text(f"Before\n\n![]({self.url})\n\nAfter")
        image = BeautifulSoup(html, "html.parser").img
        self.assertEqual(image["src"], self.url)
        self.assertEqual((image["width"], image["height"]), ("900", "1800"))
        self.assertEqual(image["loading"], "lazy")
        self.assertNotIn("srcset", image.attrs)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), checksum)
        get.assert_not_called()

    def test_raw_markup_outside_img_tags_is_preserved_and_processing_is_idempotent(self):
        html = (
            "<p data-x='a &amp; b'>Text&nbsp;<!--comment--></p>\n"
            f"<IMG SRC='{self.url}' alt='A &amp; B'/>\n"
            "<script>const s = '<img src=\"x\">';</script>\n"
            "<code>&lt;img src='x'&gt;</code>"
        )
        result = prepare_article_images(html)
        self.assertIn("<p data-x='a &amp; b'>Text&nbsp;<!--comment--></p>", result)
        self.assertIn("<script>const s = '<img src=\"x\">';</script>", result)
        self.assertIn("<code>&lt;img src='x'&gt;</code>", result)
        self.assertIn(f"SRC='{self.url}'", result)
        self.assertEqual(result.count('loading="lazy"'), 1)
        self.assertEqual(prepare_article_images(result), result)

    def test_preserves_explicit_dimensions_and_loading_policy(self):
        result = prepare_article_images(
            f'<img src="{self.url}" width="100" height="200" loading="eager">'
        )
        image = BeautifulSoup(result, "html.parser").img
        self.assertEqual((image["width"], image["height"], image["loading"]), ("100", "200", "eager"))

    def test_unknown_or_external_images_are_not_rewritten_or_fetched(self):
        for url in (
            "https://elsewhere.test/" + self.name,
            "https://media.example.test/480/" + self.name,
            "https://media.example.test/../../secret.jpg",
            "https://media.example.test/" + "b" * 64 + ".jpg",
        ):
            with self.subTest(url=url):
                self.assertIsNone(image_dimensions(url))
                self.assertEqual(preview_sources(url), "")
                image = BeautifulSoup(prepare_article_images(f'<img src="{url}">'), "html.parser").img
                self.assertEqual(image["src"], url)
                self.assertNotIn("width", image.attrs)
        self.assertEqual(pepic_filename("https://media.example.test/full/" + self.name), self.name)

    def test_previews_use_actual_portrait_widths_and_only_existing_files(self):
        self.write_image("resize/480", (240, 480))
        self.write_image("resize/960", (480, 960))
        sources = preview_sources(self.url)
        self.assertIn("/480/" + self.name + "?v=1 240w", sources)
        self.assertIn("/960/" + self.name + "?v=1 480w", sources)
        self.assertIn(self.url + " 900w", sources)
        self.assertNotIn("/1440/", sources)
        self.write_image("resize/1440", (720, 1440))
        self.assertIn("?v=1 720w", preview_sources(self.url))

    def test_new_upload_metadata_is_visible_after_an_initial_miss(self):
        url = self.url.replace("a" * 64, "c" * 64)
        self.assertIsNone(image_dimensions(url))
        path = storage_path("c" * 64 + ".jpg")
        path.parent.mkdir(parents=True)
        Image.new("RGB", (600, 400)).save(path)
        self.assertEqual(image_dimensions(url), (600, 400))

    def test_only_homepage_cards_get_previews_and_only_first_is_prioritized(self):
        self.write_image("resize/480", (240, 480))
        post = Post(type="blog", slug="test", image=self.url, title="Title", data={})
        for template in ("aspect", "horizontal", "vertical"):
            path = f"posts/cards/{template}.html"
            with self.subTest(template=template):
                listing = BeautifulSoup(render_to_string(path, {"post": post}), "html.parser")
                self.assertIsNone(listing.select_one(".card-image"))
                self.assertIn(self.url, listing.a["style"])
                for eager in (True, False):
                    homepage = BeautifulSoup(render_to_string(path, {
                        "post": post, "home_previews": True,
                        "card_eager": eager, "card_sizes": "300px",
                    }), "html.parser")
                    image = homepage.select_one(".card-image")
                    self.assertEqual(image["loading"], "eager")
                    self.assertEqual(image.get("fetchpriority"), "high" if eager else None)
                    self.assertIn("240w", image["srcset"])
                    self.assertNotIn("background-image", homepage.a.get("style", ""))

    def test_both_article_cover_layouts_keep_original_and_high_priority(self):
        post = Post(type="blog", slug="test", image=self.url, title="Title", data={})
        for style in ("cover", "simple"):
            html = render_to_string(f"posts/full/headlines/headline-{style}.html", {"post": post})
            image = BeautifulSoup(html, "html.parser").select_one(".the-cover")
            self.assertEqual(image["src"], self.url)
            self.assertEqual(image["fetchpriority"], "high")
            self.assertEqual(image["loading"], "eager")
            self.assertNotIn("srcset", image.attrs)

    def test_homepage_loads_all_cards_immediately_and_only_prioritizes_top_card(self):
        post = Post(type="blog", slug="test", image=self.url, title="Title", data={})
        html = render_to_string("index.html", {"blocks": [
            {"template": "index/main.html", "post": post},
            {"template": "index/posts3.html", "posts": [post, post]},
        ]})
        images = BeautifulSoup(html, "html.parser").select(".card-image")
        self.assertEqual(len(images), 3)
        self.assertEqual([image["loading"] for image in images], ["eager"] * 3)
        self.assertEqual([image.get("fetchpriority") for image in images], ["high", None, None])
        self.assertTrue(all(image["sizes"] for image in images))

    def test_refresh_cache_does_not_save_or_update_post_text_dates(self):
        date = datetime(2020, 1, 1)
        post = Post(
            type="blog", text=f"![]({self.url})", html_cache="<p>Old</p>",
            created_at=date, updated_at=date, published_at=date,
        )
        raw = Post(is_raw_html=True, text="<img src='external.jpg'>")
        before = post.__dict__.copy()
        with patch.object(Post, "save") as save, patch.object(Post.objects, "filter") as lookup:
            lookup.return_value.update.return_value = 1
            self.assertEqual(refresh_cache([post, raw]), 1)
            update = lookup.return_value.update.call_args.kwargs
            self.assertEqual(set(update), {"html_cache"})
            self.assertIn('loading="lazy"', update["html_cache"])
            save.assert_not_called()
        self.assertEqual(post.__dict__, before)

    def test_raw_posts_gain_loading_attributes_without_changing_saved_text(self):
        post = Post(is_raw_html=True, text=f'<img src="{self.url}">')
        original = post.text
        with patch.object(Post, "save") as save:
            html = show_post(Context({}), post)
        self.assertIn('loading="lazy"', html)
        self.assertEqual(post.text, original)
        save.assert_not_called()
