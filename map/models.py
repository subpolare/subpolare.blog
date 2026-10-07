import math

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone, translation


def validate_latitude(value):
    if not math.isfinite(value) or not -90 <= value <= 90:
        raise ValidationError("Широта должна быть конечным числом от −90 до 90.")


def validate_longitude(value):
    if not math.isfinite(value) or not -180 <= value <= 180:
        raise ValidationError("Долгота должна быть конечным числом от −180 до 180.")


validate_color = RegexValidator(r"\A#[0-9a-fA-F]{6}\Z", "Укажите цвет в формате #RRGGBB.")


class MapMarkerQuerySet(models.QuerySet):
    def public(self):
        return self.filter(
            is_enabled=True, post__is_visible=True, post__is_members_only=False,
            post__published_at__lte=timezone.now(), post__lang=translation.get_language(),
        )


class MapMarker(models.Model):
    class PreviewMode(models.TextChoices):
        ARTICLE = "article", "Из статьи"
        CUSTOM = "custom", "Своё"

    post = models.OneToOneField("posts.Post", on_delete=models.CASCADE, related_name="map_marker", verbose_name="Статья")
    latitude = models.FloatField("Широта", validators=[validate_latitude])
    longitude = models.FloatField("Долгота", validators=[validate_longitude])
    color = models.CharField("Цвет колец", max_length=7, default="#333333", validators=[validate_color])
    is_enabled = models.BooleanField("Включена", default=True)
    preview_mode = models.CharField("Превью", max_length=7, choices=PreviewMode.choices, default=PreviewMode.ARTICLE)
    preview = models.BinaryField("Подготовленное превью", default=bytes, blank=True)
    updated_at = models.DateTimeField("Обновлена", auto_now=True)

    objects = MapMarkerQuerySet.as_manager()

    class Meta:
        verbose_name = "точка"
        verbose_name_plural = "точки"
        ordering = ("pk",)
        constraints = [
            models.CheckConstraint(condition=models.Q(latitude__gte=-90, latitude__lte=90), name="map_latitude_range"),
            models.CheckConstraint(condition=models.Q(longitude__gte=-180, longitude__lte=180), name="map_longitude_range"),
        ]

    def __str__(self):
        return self.post.title or self.post.slug

    def save(self, *args, **kwargs):
        # Also validate programmatic writes; database constraints protect bulk writes.
        validate_latitude(self.latitude)
        validate_longitude(self.longitude)
        validate_color(self.color)
        return super().save(*args, **kwargs)
