from pathlib import Path
import time
from uuid import UUID

from django.conf import settings
from django.core import signing
from django.core.exceptions import RequestDataTooBig
from django.db import connection, DatabaseError, transaction
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_safe

from mirrors.models import LocalPostViews
from mirrors.view_counts import BATCH_SIZE, MAX_BODY_SIZE, MAX_COUNT, SIGNING_SALT, merge_totals
from posts.models import Post

MEDIA_MAX_AGE = 180
REPLICATION_MAX_AGE = 120


@csrf_exempt
@never_cache
@require_POST
def receive_views(request):
    # Machine-to-machine requests authenticate the entire body with the shared
    # mirror key and a separate signing salt; cookies confer no access here.
    if settings.SITE_REGION != "ru":
        return JsonResponse({"error": "RU only"}, status=403)
    if not settings.MIRROR_SIGNING_KEY:
        return JsonResponse({"error": "Synchronization is not configured"}, status=503)
    try:
        if int(request.META.get("CONTENT_LENGTH") or 0) > MAX_BODY_SIZE:
            raise RequestDataTooBig()
        body = request.body
        if len(body) > MAX_BODY_SIZE:
            raise RequestDataTooBig()
        payload = signing.loads(body.decode("ascii"), key=settings.MIRROR_SIGNING_KEY,
            salt=SIGNING_SALT, max_age=300)
    except RequestDataTooBig:
        return JsonResponse({"error": "Batch too large"}, status=413)
    except (signing.BadSignature, UnicodeError, ValueError):
        return JsonResponse({"error": "Invalid signature"}, status=403)
    try:
        if not isinstance(payload, dict) or set(payload) != {"region", "views"} or payload["region"] != "com":
            raise ValueError()
        batch = payload["views"]
        if not isinstance(batch, list) or not 1 <= len(batch) <= BATCH_SIZE:
            raise ValueError()
        counts = {}
        for row in batch:
            if not isinstance(row, dict) or set(row) != {"post_id", "count"}:
                raise ValueError()
            post_id = UUID(row["post_id"]) if isinstance(row["post_id"], str) else None
            count = row["count"]
            if post_id is None or post_id in counts or type(count) is not int or not 0 <= count <= MAX_COUNT:
                raise ValueError()
            counts[post_id] = count
    except ValueError:
        return JsonResponse({"error": "Invalid batch"}, status=400)
    with transaction.atomic():
        # Deleted posts may still have local counters on COM. Ignore those;
        # don't let delayed analytics recreate a deleted article.
        existing = set(Post.objects.filter(pk__in=counts).values_list("pk", flat=True))
        local = dict(LocalPostViews.objects.filter(post_id__in=existing).values_list("post_id", "count"))
        merge_totals([(post_id, local.get(post_id, 0), count)
            for post_id, count in counts.items() if post_id in existing])
    return JsonResponse({"ok": True})


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
