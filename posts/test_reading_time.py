from django.test import SimpleTestCase

from posts.models import Post


class ReadingTimeTests(SimpleTestCase):
    def test_rounds_up_at_1500_characters_without_rounding_to_tens(self):
        for count, expected in ((1, 1), (1500, 1), (1501, 2), (16500, 11), (16501, 12)):
            with self.subTest(count=count):
                self.assertEqual(Post(text="я" * count).reading_time, expected)

    def test_empty_posts_keep_one_minute_minimum(self):
        for text in (None, "", " \n\t"):
            with self.subTest(text=text):
                self.assertEqual(Post(text=text).reading_time, 1)

    def test_counts_rendered_markdown_without_syntax_or_link_targets(self):
        text = "# " + "я" * 1499 + "\n\n[**я**](https://example.test/" + "x" * 2000 + ")"
        self.assertEqual(Post(text=text).reading_time, 1)

    def test_decodes_entities_and_ignores_all_whitespace(self):
        text = "<p>" + "я &amp;&#32;\t\n&nbsp;&#x2003;" * 750 + "</p>"
        self.assertEqual(Post(text=text, is_raw_html=True).reading_time, 1)

    def test_counts_inline_and_fenced_code_including_escaped_html(self):
        for text in ("`<tag>`", "```html\n<tag>\n```"):
            with self.subTest(text=text):
                post = Post(text="я" * 1499 + "\n\n" + text)
                self.assertEqual(post.reading_time, 2)

    def test_images_add_no_time_but_visible_captions_count(self):
        text = "я" * 1500 + "\n\n"
        images = "![](https://example.test/image.jpg)\n\n" * 100
        self.assertEqual(Post(text=text + images).reading_time, 1)
        self.assertEqual(Post(text=text + '![я](https://example.test/image.jpg)').reading_time, 2)
        html_images = '<img src="https://example.test/image.jpg" alt="Not a caption">' * 100
        self.assertEqual(Post(text=text + html_images, is_raw_html=True).reading_time, 1)

    def test_excludes_html_attributes_comments_and_non_article_content(self):
        html = '<p title="' + "x" * 2000 + '">' + "я" * 1500 + "</p>"
        for tag in ("script", "style", "template"):
            html += f"<{tag}>" + "x" * 2000 + f"</{tag}>"
        html += "<!--" + "x" * 2000 + "-->"
        self.assertEqual(Post(text=html, is_raw_html=True).reading_time, 1)

    def test_uses_current_text_without_mutating_html_cache(self):
        post = Post(text="я" * 1501, html_cache="<p>Old cache</p>")
        before = post.__dict__.copy()
        self.assertEqual(post.reading_time, 2)
        self.assertEqual(post.__dict__, before)
