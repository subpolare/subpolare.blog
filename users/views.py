from django.http import HttpResponse


def robots(request):
    lines = [
        "User-agent: *",
        f"Host: https://{request.get_host()}",
        f"Sitemap: https://{request.get_host()}/sitemap.xml",
        "Disallow: /clickers/",
        "Disallow: /auth/",
        "Clean-param: comment_order&goto&preview /",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")
