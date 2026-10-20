from django.db import migrations


def remove_comment_reactions(apps, schema_editor):
    Clicker = apps.get_model("clickers", "Clicker")
    Clicker.objects.using(schema_editor.connection.alias).filter(comment__isnull=False).delete()


class Migration(migrations.Migration):
    dependencies = [("clickers", "0003_alter_clicker_block_alter_clicker_comment")]
    operations = [
        migrations.RunPython(remove_comment_reactions, migrations.RunPython.noop),
        migrations.RemoveField(model_name="clicker", name="comment"),
    ]
