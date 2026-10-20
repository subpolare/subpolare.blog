import os
from pathlib import Path
import subprocess
import sys
import textwrap

from django.test import SimpleTestCase

from common.markdown.markdown import markdown_snippet, markdown_text


class MarkdownRegressionTests(SimpleTestCase):
    def test_unclosed_link_titles_finish_without_exponential_backtracking(self):
        # CVE-2026-33079: both quote styles and reference definitions reach
        # the vulnerable title parser. A subprocess bounds regressions safely.
        code = textwrap.dedent(r'''
            import django
            django.setup()
            from common.markdown.markdown import (
                markdown_snippet, markdown_plain, markdown_text,
            )

            for render in (markdown_text, markdown_snippet, markdown_plain):
                for quote in ('"', "'"):
                    title = quote + '\\!' * 40
                    for source in ('[x](y ' + title + ')', '[x]: y ' + title):
                        assert isinstance(render(source), str)
            print('ok')
        ''')
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "DJANGO_SETTINGS_MODULE": "subpolare.test_settings"},
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "ok")

    def test_valid_quoted_link_titles_still_render(self):
        for render in (markdown_text, markdown_snippet):
            for quote in ('"', "'"):
                title = quote + r'escaped\! title' + quote
                for source in (
                    '[x](https://example.test ' + title + ')',
                    '[x][ref]\n\n[ref]: https://example.test ' + title,
                ):
                    with self.subTest(renderer=render.__name__, source=source):
                        self.assertEqual(
                            render(source),
                            '<p><a href="https://example.test">x</a></p>\n',
                        )

    def test_custom_article_plugins_preserve_nested_markdown(self):
        cases = (
            ('[[[note\n**Text**\n]]]',
             '<div class="block-text note" id=""><p><strong>Text</strong></p>\n</div>\n'),
            ('{{{wide\n**Media**\n}}}',
             '<div class="block-media wide" id=""><strong>Media</strong>\n</div>\n'),
            ('% **Quote**',
             '<div class="block-cite"><p><strong>Quote</strong></p>\n</div>\n'),
            ('[? **Secret** ?]',
             '<p><span class="block-spoiler"><span class="block-spoiler-button">?</span>'
             '<span class="block-spoiler-text"> <strong>Secret</strong> </span></span>\n\n</p>\n'),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(markdown_text(source), expected)

    def test_snippets_escape_html_and_keep_markdown_formatting(self):
        html = markdown_snippet('<script>alert(1)</script>\n\n**Bold** and ~~gone~~')
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('<strong>Bold</strong> and <del>gone</del>', html)
