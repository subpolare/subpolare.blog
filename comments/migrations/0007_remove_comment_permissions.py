from django.db import migrations


def remove_comment_permissions(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    ContentType.objects.using(schema_editor.connection.alias).filter(
        app_label="comments", model="comment",
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("comments", "0006_delete_comment"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]
    operations = [migrations.RunPython(remove_comment_permissions, migrations.RunPython.noop)]
