import hashlib

from django.http import HttpResponse, HttpResponseNotModified, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.cache import patch_cache_control, patch_vary_headers
from django.utils.http import parse_etags
from django.views.decorators.http import require_GET

from .access import is_map_admin, safe_post_url
from .models import MapMarker, MapPlace
from .previews import placeholder


def public_markers():
    markers = MapMarker.objects.public().select_related("post").only(
        "id", "latitude", "longitude", "color", "updated_at", "post__title", "post__slug", "post__type", "post__url",
    )
    for marker in markers:
        url = safe_post_url(marker.post)
        if url:
            yield {
                "id": marker.pk, "latitude": marker.latitude, "longitude": marker.longitude,
                "title": marker.post.title or marker.post.slug, "url": url, "color": marker.color,
                "preview": reverse("map:preview", args=[marker.pk]) + "?v=" + str(int(marker.updated_at.timestamp() * 1000000)),
            }


@require_GET
def markers(request):
    response = JsonResponse(list(public_markers()), safe=False)
    patch_cache_control(response, no_store=True)
    return response


@require_GET
def places(request):
    response = JsonResponse(list(MapPlace.objects.filter(is_enabled=True, kind__in=[MapPlace.Kind.CITY, MapPlace.Kind.COUNTRY]).values(
        "id", "name", "kind", "latitude", "longitude", "note",
    )), safe=False)
    patch_cache_control(response, no_store=True)
    return response


@require_GET
def preview(request, marker_id):
    owner = is_map_admin(request.user)
    queryset = MapMarker.objects.all() if owner else MapMarker.objects.public()
    marker = get_object_or_404(queryset, pk=marker_id)
    data = bytes(marker.preview) or placeholder()
    etag = '"' + hashlib.sha256(data).hexdigest() + '"'
    matches = parse_etags(request.headers.get("If-None-Match", ""))
    response = HttpResponseNotModified() if "*" in matches or etag in [value.removeprefix("W/") for value in matches] else HttpResponse(data, content_type="image/webp")
    response["ETag"] = etag
    response["X-Content-Type-Options"] = "nosniff"
    patch_cache_control(response, private=True, no_cache=True, must_revalidate=True, **({"no_store": True} if owner else {}))
    patch_vary_headers(response, ["Cookie", "Accept-Language"])
    return response
