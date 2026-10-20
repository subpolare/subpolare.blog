"""Migration-only app: retained so existing databases can drop retired tables."""
from django.apps import AppConfig


class CommentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "comments"
