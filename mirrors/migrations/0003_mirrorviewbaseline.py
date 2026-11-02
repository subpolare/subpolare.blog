from django.conf import settings
from django.db import migrations, models


def capture_com_baseline(apps, schema_editor):
    if settings.SITE_REGION != "com":
        return
    LocalViews = apps.get_model("mirrors", "LocalPostViews")
    Totals = apps.get_model("mirrors", "PostViewTotals")
    Baseline = apps.get_model("mirrors", "MirrorViewBaseline")
    alias = schema_editor.connection.alias
    if Totals.objects.using(alias).filter(com_count__gt=0).exists():
        raise RuntimeError("COM views already accepted by RU; refusing to reset their starting point.")
    Baseline.objects.using(alias).bulk_create([
        Baseline(post_id=row.post_id, count=row.count)
        for row in LocalViews.objects.using(alias).all().iterator()
    ])


class Migration(migrations.Migration):
    dependencies = [("mirrors", "0002_postviewtotals")]
    operations = [
        migrations.CreateModel(name="MirrorViewBaseline", fields=[
            ("post_id", models.UUIDField(primary_key=True, serialize=False)),
            ("count", models.PositiveBigIntegerField(default=0)),
        ]),
        migrations.RunPython(capture_com_baseline, migrations.RunPython.noop),
    ]
