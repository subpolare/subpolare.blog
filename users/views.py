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


def yandex_verification(request):
    content = (
        "<html>"
        "<head><meta http-equiv=\"Content-Type\" content=\"text/html; charset=UTF-8\"></head>"
        "<body>Verification: 5a8ac3fe600ec2e1</body>"
        "</html>"
    )
    return HttpResponse(content, content_type="text/html")