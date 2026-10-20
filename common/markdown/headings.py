"""Upgrade cached Markdown headings without rewriting the rest of the article."""
import re
from html.parser import HTMLParser


class _CachedHeadings(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=False)
        self.html = html
        self.offsets = [0]
        for line in html.split("\n"):
            self.offsets.append(self.offsets[-1] + len(line) + 1)
        self.divs = []
        self.replacements = []

    def position(self):
        line, column = self.getpos()
        return self.offsets[line - 1] + column

    def handle_starttag(self, tag, attrs):
        if tag != "div":
            return
        start = self.position()
        opening = self.get_starttag_text()
        match = re.fullmatch(r'<div class="header-([1-6])" id="([^"]*)">', opening)
        # Only the exact wrapper and self-link emitted by the old renderer.
        if match and self.html.startswith(f'<a href="#{match[2]}">', start + len(opening)):
            self.divs.append((start, match[1]))
        else:
            self.divs.append(None)

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag != "div" or not self.divs:
            return
        heading = self.divs.pop()
        if heading:
            start, level = heading
            end = self.position()
            self.replacements.extend(((start + 1, start + 4, f"h{level}"),
                                      (end + 2, end + 5, f"h{level}")))


def semantic_headings(html):
    if '<div class="header-' not in html:
        return html
    parser = _CachedHeadings(html)
    parser.feed(html)
    parser.close()
    for start, end, replacement in sorted(parser.replacements, reverse=True):
        html = html[:start] + replacement + html[end:]
    return html
