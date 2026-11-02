from django.conf import settings
from django.db import migrations, models


def seed_ru_views(apps, schema_editor):
    if settings.SITE_REGION != "ru":
        # The subscriber must be empty for the initial replication copy.
        return
    LocalViews = apps.get_model("mirrors", "LocalPostViews")
    Totals = apps.get_model("mirrors", "PostViewTotals")
    alias = schema_editor.connection.alias
    Totals.objects.using(alias).bulk_create([
        Totals(post_id=row.post_id, ru_count=row.count)
        for row in LocalViews.objects.using(alias).all().iterator()
    ])


class Migration(migrations.Migration):
    dependencies = [("mirrors", "0001_local_views")]
    operations = [
        migrations.CreateModel(name="PostViewTotals", fields=[
            ("post_id", models.UUIDField(primary_key=True, serialize=False)),
            ("ru_count", models.PositiveBigIntegerField(default=0)),
            ("com_count", models.PositiveBigIntegerField(default=0)),
        ]),
        migrations.RunPython(seed_ru_views, migrations.RunPython.noop),
    ]
