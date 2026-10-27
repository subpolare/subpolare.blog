"""Choose an available mirror, preserving the requested public resource."""
from django.conf import settings
from django.core import signing
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseForbidden
from django.utils.cache import patch_vary_headers

from mirrors import geo
from utils.request import parse_ip_address

HOSTS = {"ru": "subpolare.ru", "com": "subpolare.com"}
EXCLUDED = ("/godmode/", "/editor/", "/clickers/", "/map/", "/static/", "/media/", "/legacy/", "/_mirror/", "/rss/")


def public_navigation(request):
    return (request.method in ("GET", "HEAD")
            and not request.path.startswith(EXCLUDED)
            and "/edit/" not in request.path
            and request.path not in ("/robots.txt", "/sitemap.xml", "/yandex_5a8ac3fe600ec2e1.html")
            and not request.GET.get("preview"))


def redirect_to(request, region, **extra):
    query = request.GET.copy()
    for key in ("mirror", "_mirror_hop"):
        query.pop(key, None)
    query.update(extra)
    location = "https://" + HOSTS[region] + request.path
    if query:
        location += "?" + query.urlencode()
    if request.headers.get("HX-Request") == "true":
        # Cross-origin XHR redirects cannot navigate the browser and may fail
        # CORS. Let htmx perform a full navigation, retaining the same URL.
        response = HttpResponse()
        response["HX-Redirect"] = location
    else:
        response = HttpResponseRedirect(location)
    response["Cache-Control"] = "private, no-store"
    response["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


class MirrorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(":")[0]
        current = next((r for r, h in HOSTS.items() if host in (h, "www." + h)), None)
        # The foreign instance must never edit replicated content, even if an
        # administrator manually submits a URL or forges an authenticated cookie.
        if settings.SITE_REGION == "com" and (
            request.path.startswith(("/godmode/", "/editor/")) or "/edit/" in request.path
        ):
            if request.method in ("GET", "HEAD"):
                return redirect_to(request, "ru")
            return HttpResponseForbidden("Editing is available on subpolare.ru only.")

        if current and public_navigation(request):
            chosen = request.GET.get("mirror")
            if chosen in HOSTS:
                if chosen != current:
                    return redirect_to(request, chosen, mirror=chosen)
                response = redirect_to(request, current)
                response.set_cookie("mirror", chosen, max_age=365 * 86400, secure=True, httponly=True, samesite="Lax")
                return response
            hop = request.GET.get("_mirror_hop")
            if hop:
                try:
                    data = signing.loads(hop, key=settings.MIRROR_SIGNING_KEY, salt="mirror-hop", max_age=60)
                    if data == {"region": current, "path": request.path}:
                        response = redirect_to(request, current)
                        response.set_cookie("mirror_arrived", current, max_age=120, secure=True, httponly=True, samesite="Lax")
                        return response
                except signing.BadSignature:
                    pass
            preferred = request.COOKIES.get("mirror")
            if preferred not in HOSTS:
                preferred = None
            if settings.GEO_REDIRECT_ENABLED and request.COOKIES.get("mirror_arrived") != current:
                ip = parse_ip_address(request)
                code = geo.country(ip)
                target = preferred or ("ru" if code == "RU" else "com" if code else current)
                if target != current and not geo.verified_crawler(ip) and geo.target_available():
                    token = signing.dumps({"region": target, "path": request.path}, key=settings.MIRROR_SIGNING_KEY, salt="mirror-hop")
                    return redirect_to(request, target, _mirror_hop=token)

        response = self.get_response(request)
        if current and public_navigation(request):
            # A shared proxy cache must not replay a geographically selected response.
            response["Cache-Control"] = "private, no-store"
            patch_vary_headers(response, ("Cookie",))
        if settings.SITE_REGION == "com" and not response.streaming:
            content_type = response.get("Content-Type", "")
            if "text/html" in content_type or "application/json" in content_type or "application/xml" in content_type:
                content = response.content
                # Rewrite only owned media origins, after rendering; database
                # content and cached Markdown remain identical on both mirrors.
                for scheme in (b"https://", b"http://", b"//"):
                    content = content.replace(scheme + b"media.subpolare.ru/", b"https://subpolare.com/media/")
                    content = content.replace(scheme + b"i.subpolare.ru/", b"https://subpolare.com/legacy/")
                response.content = content
                if response.has_header("Content-Length"):
                    response["Content-Length"] = str(len(content))
        return response
