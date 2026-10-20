from django.db import migrations, models

from posts.reading_time import calculate_reading_time


def populate_reading_time(apps, schema_editor):
    Post = apps.get_model("posts", "Post")
    posts = Post.objects.using(schema_editor.connection.alias)
    batch = []
    for post in posts.only("id", "text", "is_raw_html").iterator(chunk_size=200):
        post.reading_time = calculate_reading_time(post.text, post.is_raw_html)
        batch.append(post)
        if len(batch) == 200:
            posts.bulk_update(batch, ["reading_time"], batch_size=200)
            batch = []
    if batch:
        posts.bulk_update(batch, ["reading_time"], batch_size=200)


class Migration(migrations.Migration):
    dependencies = [
        ("posts", "0004_alter_post_slug_alter_post_unique_together"),
    ]

    operations = [
        migrations.AddField(
            model_name="post",
            name="reading_time",
            field=models.PositiveIntegerField(default=5, editable=False),
        ),
        migrations.RunPython(populate_reading_time, migrations.RunPython.noop),
    ]
