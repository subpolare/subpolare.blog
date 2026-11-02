"""Monotonic local counters and the RU-owned, replicated total."""
from django.conf import settings
from django.db import connection, transaction

from mirrors.models import LocalPostViews, MirrorViewBaseline

SIGNING_SALT = "mirror-view-counts-v1"
BATCH_SIZE = 250
MAX_BODY_SIZE = 64 * 1024
MAX_COUNT = 2**63 - 1


def merge_totals(rows):
    """Merge (post_id, ru_count, com_count) snapshots without losing concurrent writes."""
    if settings.SITE_REGION != "ru":
        raise ValueError("Only RU may write view totals")
    with connection.cursor() as cursor:
        # Stable lock order also makes overlapping concurrent batches safe.
        cursor.executemany("""
            INSERT INTO mirrors_postviewtotals (post_id, ru_count, com_count)
            VALUES (%s, %s, %s)
            ON CONFLICT (post_id) DO UPDATE SET
                ru_count = GREATEST(mirrors_postviewtotals.ru_count, EXCLUDED.ru_count),
                com_count = GREATEST(mirrors_postviewtotals.com_count, EXCLUDED.com_count)
            WHERE mirrors_postviewtotals.ru_count < EXCLUDED.ru_count
               OR mirrors_postviewtotals.com_count < EXCLUDED.com_count
        """, sorted(rows, key=lambda row: str(row[0])))


@transaction.atomic
def record_view(post_id):
    with connection.cursor() as cursor:
        cursor.execute("""
            INSERT INTO mirrors_localpostviews (post_id, count) VALUES (%s, 1)
            ON CONFLICT (post_id) DO UPDATE
            SET count = mirrors_localpostviews.count + 1
            RETURNING count
        """, [post_id])
        count = cursor.fetchone()[0]
    if settings.SITE_REGION == "ru":
        merge_totals([(post_id, count, 0)])


def local_snapshots():
    """Bound memory and request size, including when backfilling old counters."""
    last_id = None
    while True:
        rows = LocalPostViews.objects.order_by("post_id")
        if last_id is not None:
            rows = rows.filter(post_id__gt=last_id)
        batch = list(rows.values_list("post_id", "count")[:BATCH_SIZE])
        if not batch:
            return
        if settings.SITE_REGION == "com":
            baselines = dict(MirrorViewBaseline.objects.filter(
                post_id__in=[post_id for post_id, _ in batch]
            ).values_list("post_id", "count"))
            yield [(post_id, max(0, count - baselines.get(post_id, 0))) for post_id, count in batch]
        else:
            yield batch
        last_id = batch[-1][0]


def reconcile_ru_views():
    for batch in local_snapshots():
        merge_totals([(post_id, count, 0) for post_id, count in batch])
