from pathlib import Path

from django.conf import settings
from django.db import connection, DatabaseError
from django.http import JsonResponse
from django.views.decorators.http import require_safe


@require_safe
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT EXISTS(SELECT 1 FROM posts)")
            ready = cursor.fetchone()[0]
        if settings.SITE_REGION == "com":
            ready = ready and (Path(settings.PEPIC_STORAGE_ROOT) / ".mirror-synced").exists()
    except DatabaseError:
        ready = False
    response = JsonResponse({"ready": bool(ready), "region": settings.SITE_REGION})
    response["Cache-Control"] = "no-store"
    return response if ready else JsonResponse({"ready": False}, status=503)
