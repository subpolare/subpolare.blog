from urllib.parse import urlsplit


def is_map_admin(user):
    return bool(user.is_authenticated and user.is_active and user.is_staff and user.is_superuser)


def safe_post_url(post):
    url = post.get_absolute_url()
    if not url or any(ord(char) <= 32 or ord(char) == 127 for char in url) or "\\" in url:
        return None
    try:
        parsed = urlsplit(url)
        if url.startswith("/") and not url.startswith("//"):
            return url
        if parsed.scheme in ("https", "http") and parsed.hostname and not parsed.username and not parsed.password:
            return url
    except ValueError:
        pass
    return None
