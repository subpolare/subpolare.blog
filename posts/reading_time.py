from bs4 import BeautifulSoup

from common.markdown.markdown import markdown_text


def calculate_reading_time(text, is_raw_html=False):
    html = text or ""
    if not is_raw_html:
        html = markdown_text(html)

    # Decode entities without treating escaped code as tags.
    soup = BeautifulSoup(html, "html.parser")
    for element in soup(["script", "style", "template"]):
        element.decompose()
    characters = sum(not character.isspace() for character in soup.get_text())
    minutes = (characters + 1499) // 1500
    return max(5, ((minutes + 2) // 5) * 5)
