from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("posts", "0005_post_reading_time")]
    operations = [
        migrations.RemoveField(model_name="post", name="comment_count"),
        migrations.RemoveField(model_name="post", name="is_commentable"),
    ]
