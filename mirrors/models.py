from django.db import models


class LocalPostViews(models.Model):
    # Deliberately outside the replicated content tables and without a foreign
    # key: subscriber inserts/deletes must never affect a local counter.
    post_id = models.UUIDField(primary_key=True)
    count = models.PositiveBigIntegerField(default=0)
