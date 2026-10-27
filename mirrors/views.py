from pathlib import Path
import time

from django.conf import settings
from django.db import connection, DatabaseError
from django.http import JsonResponse
from django.views.decorators.http import require_safe

MEDIA_MAX_AGE = 180
REPLICATION_MAX_AGE = 120


def media_fresh():
    try:
        timestamp = int((Path(settings.PEPIC_STORAGE_ROOT) / ".mirror-synced").read_text())
        return 0 <= time.time() - timestamp < MEDIA_MAX_AGE
    except (OSError, ValueError):
        return False


@require_safe
def health(request):
    readable = replication = media = False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT EXISTS(SELECT 1 FROM posts)")
            readable = bool(cursor.fetchone()[0])
            if settings.SITE_REGION == "com":
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM pg_stat_subscription
                        WHERE subname = 'blog_content_from_ru' AND relid IS NULL
                          AND pid IS NOT NULL
                          AND last_msg_receipt_time BETWEEN
                              now() - (%s * interval '1 second') AND now()
                    ) AND NOT EXISTS (
                        SELECT 1 FROM pg_subscription_rel WHERE srsubstate <> 'r'
                    )
                """, [REPLICATION_MAX_AGE])
                replication = bool(cursor.fetchone()[0])
                media = media_fresh()
            else:
                replication = media = True
    except DatabaseError:
        pass
    ready = readable and replication and media
    # Readability is deliberately independent: stale COM content can still be
    # read directly during a RU outage, but automatic routing must stop.
    response = JsonResponse({"ready": ready, "readable": readable,
        "replication_fresh": replication, "media_fresh": media,
        "region": settings.SITE_REGION}, status=200 if ready else 503)
    response["Cache-Control"] = "no-store"
    return response
