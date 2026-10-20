from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("users", "0005_user_patreon_id_user_telegram_id_and_more")]
    operations = [
        migrations.RemoveField(model_name="user", name="vas3k_club_slug"),
        migrations.RemoveField(model_name="user", name="patreon_id"),
        migrations.RemoveField(model_name="user", name="telegram_id"),
    ]
