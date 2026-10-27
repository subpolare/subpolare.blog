from django.db import migrations, models


def seed_views(apps, schema_editor):
    Post = apps.get_model("posts", "Post")
    Views = apps.get_model("mirrors", "LocalPostViews")
    alias = schema_editor.connection.alias
    Views.objects.using(alias).bulk_create([
        Views(post_id=post.pk, count=post.view_count)
        for post in Post.objects.using(alias).all().iterator()
    ], ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [("posts", "0006_remove_comment_fields")]
    operations = [
        migrations.CreateModel(name="LocalPostViews", fields=[
            ("post_id", models.UUIDField(primary_key=True, serialize=False)),
            ("count", models.PositiveBigIntegerField(default=0)),
        ]),
        migrations.RunPython(seed_views, migrations.RunPython.noop),
    ]
