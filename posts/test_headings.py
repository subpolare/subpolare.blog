from unittest.mock import patch

from bs4 import BeautifulSoup
from django.template import Context
from django.test import SimpleTestCase, override_settings

from common.markdown.headings import semantic_headings
from common.markdown.markdown import markdown_snippet, markdown_text
from posts.models import Post
from posts.templatetags.posts import show_post


class MarkdownHeadingTests(SimpleTestCase):
    def test_all_levels_keep_classes_anchors_and_inline_formatting(self):
        for renderer in (markdown_text, markdown_snippet):
            for level in range(1, 7):
                with self.subTest(renderer=renderer.__name__, level=level):
                    html = renderer(f'{"#" * level} Заголовок *курсивом*')
                    soup = BeautifulSoup(html, "html.parser")
                    heading = soup.find(f"h{level}")
                    self.assertIsNotNone(heading)
                    self.assertEqual(heading["class"], [f"header-{level}"])
                    self.assertEqual(heading.a["href"], "#" + heading["id"])
                    self.assertEqual(heading.em.text, "курсивом")
                    self.assertIsNone(soup.find("div"))

    def test_cached_headings_match_fresh_rendering(self):
        for level in range(1, 7):
            html = markdown_text(f'{"#" * level} Заголовок **жирным**')
            old = html.replace(f"<h{level} ", "<div ").replace(f"</h{level}>", "</div>")
            self.assertEqual(semantic_headings(old), html)
            self.assertEqual(semantic_headings(html), html)

    def test_table_of_contents_keeps_existing_japan_anchor_targets(self):
        text = (
            "[Осака](https://subpolare.ru/world/japan/#osaka)\n\n"
            "[Химедзи](https://subpolare.ru/world/japan/#zamok-beloi-tsapli)\n\n"
            "# Осака 🏯\n\n### 🏯 Замок Белой цапли"
        )
        soup = BeautifulSoup(markdown_text(text), "html.parser")
        for link in soup.select('p a'):
            anchor = link["href"].split("#", 1)[1]
            targets = soup.find_all(id=anchor)
            self.assertEqual(len(targets), 1)
            self.assertIn(targets[0].name, ("h1", "h3"))

    def test_conversion_preserves_other_html_byte_for_byte(self):
        heading = '<div class="header-2" id="old"><a href="#old">Old &amp; <em>new</em></a></div>'
        prefix = (
            '<!-- ' + heading + ' -->\n<script>const html = \'' + heading + "';</script>\n"
            '<div class="block-text"><div>Before</div><br />'
            '<div class="header-2" id="custom">Custom HTML</div>'
        )
        suffix = '<div data-value="&amp;">After</div></div>'
        expected = heading.replace("<div ", "<h2 ").replace("</div>", "</h2>")
        self.assertEqual(semantic_headings(prefix + heading + suffix), prefix + expected + suffix)

    @override_settings(DEBUG=False)
    def test_existing_cache_is_upgraded_without_saving_or_rerendering(self):
        old = '<div class="header-1" id="old"><a href="#old">Old</a></div>'
        post = Post(html_cache=old, text="# Different", is_raw_html=False)
        with patch.object(Post, "save") as save, patch("posts.templatetags.posts.markdown_text") as render:
            result = show_post(Context({}), post)
        self.assertIn('<h1 class="header-1"', result)
        self.assertEqual(post.html_cache, old)
        save.assert_not_called()
        render.assert_not_called()

    def test_raw_html_posts_keep_author_tags(self):
        html = '<div class="header-1" id="raw"><a href="#raw">Raw</a></div>'
        post = Post(text=html, is_raw_html=True)
        self.assertEqual(show_post(Context({}), post), html)
