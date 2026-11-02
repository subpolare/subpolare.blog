from django.db import models


class LocalPostViews(models.Model):
    # Deliberately outside the replicated content tables and without a foreign
    # key: subscriber inserts/deletes must never affect a local counter.
    post_id = models.UUIDField(primary_key=True)
    count = models.PositiveBigIntegerField(default=0)


class PostViewTotals(models.Model):
    # Written only on RU; COM receives these rows through logical replication.
    # Keep each source's cumulative count to make retries idempotent.
    post_id = models.UUIDField(primary_key=True)
    ru_count = models.PositiveBigIntegerField(default=0)
    com_count = models.PositiveBigIntegerField(default=0)


class MirrorViewBaseline(models.Model):
    # Immutable COM-only starting point, captured by the deployment migration.
    # Keep historical local reads without adding them to RU's existing total.
    post_id = models.UUIDField(primary_key=True)
    count = models.PositiveBigIntegerField(default=0)
