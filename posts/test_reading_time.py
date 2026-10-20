from unittest.mock import patch

from django.template.loader import render_to_string
from django.test import SimpleTestCase

from posts.models import Post
from posts.reading_time import calculate_reading_time


class ReadingTimeTests(SimpleTestCase):
    def test_rounds_minutes_to_nearest_five_with_five_minute_minimum(self):
        for minutes, expected in (
            (0, 5), (1, 5), (2, 5), (3, 5), (4, 5), (5, 5), (7, 5),
            (8, 10), (11, 10), (12, 10), (13, 15), (17, 15), (23, 25),
        ):
            with self.subTest(minutes=minutes):
                self.assertEqual(calculate_reading_time("я" * (minutes * 1500)), expected)

    def test_rounds_partial_minutes_up_before_rounding_to_five(self):
        self.assertEqual(calculate_reading_time("я" * 10500), 5)
        self.assertEqual(calculate_reading_time("я" * 10501), 10)

    def test_empty_posts_keep_five_minute_minimum(self):
        for text in (None, "", " \n\t"):
            with self.subTest(text=text):
                self.assertEqual(calculate_reading_time(text), 5)

    def test_counts_rendered_markdown_without_syntax_or_link_targets(self):
        text = "# " + "я" * 10499 + "\n\n[**я**](https://example.test/" + "x" * 2000 + ")"
        self.assertEqual(calculate_reading_time(text), 5)

    def test_decodes_entities_and_ignores_all_whitespace(self):
        text = "<p>" + "я &amp;&#32;\t\n&nbsp;&#x2003;" * 5250 + "</p>"
        self.assertEqual(calculate_reading_time(text, is_raw_html=True), 5)

    def test_counts_inline_and_fenced_code_including_escaped_html(self):
        for text in ("`<tag>`", "```html\n<tag>\n```"):
            with self.subTest(text=text):
                post = Post(text="я" * 10499 + "\n\n" + text)
                self.assertEqual(calculate_reading_time(post.text, post.is_raw_html), 10)

    def test_images_add_no_time_but_visible_captions_count(self):
        text = "я" * 10500 + "\n\n"
        images = "![](https://example.test/image.jpg)\n\n" * 100
        self.assertEqual(calculate_reading_time(text + images), 5)
        self.assertEqual(calculate_reading_time(text + '![я](https://example.test/image.jpg)'), 10)
        html_images = '<img src="https://example.test/image.jpg" alt="Not a caption">' * 100
        self.assertEqual(calculate_reading_time(text + html_images, is_raw_html=True), 5)

    def test_excludes_html_attributes_comments_and_non_article_content(self):
        html = '<p title="' + "x" * 2000 + '">' + "я" * 10500 + "</p>"
        for tag in ("script", "style", "template"):
            html += f"<{tag}>" + "x" * 2000 + f"</{tag}>"
        html += "<!--" + "x" * 2000 + "-->"
        self.assertEqual(calculate_reading_time(html, is_raw_html=True), 5)

    def test_uses_current_text_without_mutating_html_cache(self):
        post = Post(text="я" * 10501, html_cache="<p>Old cache</p>")
        before = post.__dict__.copy()
        self.assertEqual(calculate_reading_time(post.text, post.is_raw_html), 10)
        self.assertEqual(post.__dict__, before)

    def test_rendering_metadata_reads_saved_value_without_calculation(self):
        post = Post(text="я" * 10501, reading_time=25)
        with patch("posts.models.calculate_reading_time", side_effect=AssertionError):
            html = render_to_string("posts/full/headlines/headline-meta.html", {"post": post})
        self.assertIn("~25 минут чтения", html)

    def test_save_calculates_and_includes_reading_time_in_partial_updates(self):
        post = Post(slug="test", text="я" * 16500)
        post._state.adding = False
        with patch("django.db.models.Model.save") as save:
            post.save(update_fields=["text"])
        self.assertEqual(post.reading_time, 10)
        self.assertEqual(save.call_args.kwargs["update_fields"], {"text", "reading_time"})

    def test_cache_and_counter_saves_do_not_recalculate(self):
        post = Post(slug="test", text="я" * 16500, reading_time=25)
        post._state.adding = False
        for kwargs in ({"flush_cache": False}, {"update_fields": ["view_count"]}, {"update_fields": []}):
            with self.subTest(kwargs=kwargs):
                with patch("posts.models.calculate_reading_time", side_effect=AssertionError):
                    with patch("django.db.models.Model.save"):
                        post.save(**kwargs)
                self.assertEqual(post.reading_time, 25)
