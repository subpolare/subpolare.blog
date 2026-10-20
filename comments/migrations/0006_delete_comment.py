from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("comments", "0005_alter_comment_options"),
        ("clickers", "0004_remove_comment_reactions"),
    ]
    operations = [migrations.DeleteModel(name="Comment")]
