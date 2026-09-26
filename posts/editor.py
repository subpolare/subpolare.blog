"""Admin-only Markdown preview and the Club's Pepic upload contract."""
from functools import wraps
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.template import Context
from django.utils.translation import get_language
from django.views.decorators.debug import sensitive_variables
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache

from common.markdown.markdown import markdown_text
from posts.models import Post
from posts.templatetags.posts import render_post_blocks

IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"}
# Leave room for multipart headers below nginx's existing client_max_body_size 15M.
MAX_IMAGE_SIZE = 14 * 1024 * 1024


def admin_only(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_superuser:
            return HttpResponseForbidden()
        return view(request, *args, **kwargs)
    return wrapped


@never_cache
@admin_only
@require_POST
def preview_post(request, post_type, post_slug):
    post = get_object_or_404(Post, type=post_type, slug=post_slug, lang=get_language())
    text = request.POST.get("text", "")
    if len(text) > 100000:
        return JsonResponse({"error": "Текст слишком длинный"}, status=400)
    # Never call show_post: it writes html_cache, timestamps and view counts.
    html = text if post.is_raw_html else markdown_text(text)
    html = render_post_blocks(Context({
        "post": post, "clickers": {}, "user_votes": set(), "cookies": {}, "comments": [],
    }), html)
    document = render_to_string("posts/editor-preview.html", {
        "html": html, "post": post,
    }, request=request)
    return JsonResponse({"html": document})


@never_cache
@admin_only
@require_POST
@sensitive_variables()
def upload_post_image(request):
    media = request.FILES.get("media")
    if not media or media.content_type not in IMAGE_TYPES:
        return JsonResponse({"error": "Выберите изображение JPEG, PNG, WebP или GIF"}, status=400)
    if not media.size or media.size > MAX_IMAGE_SIZE:
        return JsonResponse({"error": "Нужен непустой файл размером до 14 МБ"}, status=413)
    url = settings.PEPIC_UPLOAD_URL
    if not url or not settings.PEPIC_UPLOAD_CODE:
        return JsonResponse({"error": "Загрузка не настроена на сервере"}, status=503)
    if urlsplit(url).scheme != "https" or not urlsplit(url).netloc:
        return JsonResponse({"error": "Некорректная настройка хранилища"}, status=503)
    try:
        # No redirects: never forward the server credential to another host.
        with requests.post(
            url,
            files={"media": (media.name, media.file, media.content_type)},
            data={"code": settings.PEPIC_UPLOAD_CODE},
            headers={"Accept": "application/json"},
            timeout=(5, 45), allow_redirects=False,
        ) as response:
            if response.status_code not in (200, 201):
                return JsonResponse({"error": "Хранилище отклонило загрузку"}, status=502)
            result = response.json()
            uploaded = result.get("uploaded") if isinstance(result, dict) else None
            if not isinstance(uploaded, str):
                raise ValueError("Invalid upload response")
            parsed = urlsplit(uploaded)
            if parsed.scheme not in ("http", "https") or not parsed.netloc or any(
                char.isspace() or ord(char) < 32 or char in "<>\"'()\\" for char in uploaded
            ):
                raise ValueError("Invalid upload URL")
    except (requests.RequestException, ValueError):
        # Do not log upstream bodies/exceptions: they may contain the upload code.
        return JsonResponse({"error": "Не удалось загрузить файл. Попробуйте ещё раз"}, status=502)
    return JsonResponse({"uploaded": uploaded})
