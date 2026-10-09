from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_GET

from .access import is_map_admin
from .forms import MapMarkerForm
from .models import MapMarker, MapPlace
from .previews import update_preview


@admin.register(MapPlace)
class MapPlaceAdmin(admin.ModelAdmin):
    change_form_template = "admin/map/change_form.html"
    list_display = ("name", "latitude", "longitude", "note", "is_enabled")
    list_filter = ("is_enabled",)
    search_fields = ("name", "note")
    fields = ("name", ("latitude", "longitude"), "note", "is_enabled")

    def has_module_permission(self, request):
        return is_map_admin(request.user)

    def has_view_permission(self, request, obj=None):
        return is_map_admin(request.user)

    has_add_permission = has_view_permission
    has_change_permission = has_view_permission
    has_delete_permission = has_view_permission


@admin.register(MapMarker)
class MapMarkerAdmin(admin.ModelAdmin):
    form = MapMarkerForm
    change_list_template = "admin/map/change_list.html"
    change_form_template = "admin/map/change_form.html"
    list_display = ("article", "publication_status", "latitude", "longitude", "is_enabled", "preview_mode", "updated_at")
    list_filter = ("is_enabled",)
    search_fields = ("post__title", "post__slug")
    list_select_related = ("post",)
    readonly_fields = ("prepared_preview", "updated_at")
    fields = ("post", ("latitude", "longitude"), "color", "is_enabled", "preview_mode", "custom_image", "prepared_preview", "updated_at")
    actions = ("refresh_previews",)

    def has_module_permission(self, request):
        return is_map_admin(request.user)

    def has_view_permission(self, request, obj=None):
        return is_map_admin(request.user)

    has_add_permission = has_view_permission
    has_change_permission = has_view_permission
    has_delete_permission = has_view_permission

    @admin.display(description="Статья", ordering="post__title")
    def article(self, obj):
        return f"{obj.post.title or obj.post.slug} ({obj.post.lang})"

    @admin.display(description="Статус статьи")
    def publication_status(self, obj):
        if obj.post.is_members_only:
            return "Закрытая"
        if not obj.post.is_visible:
            return "Черновик"
        if obj.post.published_at > timezone.now():
            return "Запланирована"
        return "Опубликована"

    @admin.display(description="Сохранённое превью")
    def prepared_preview(self, obj):
        if not obj.pk:
            return "Будет подготовлено при сохранении"
        return format_html('<img src="{}?v={}" width="128" height="128" alt="Превью">', reverse("map:preview", args=[obj.pk]), obj.updated_at.timestamp())

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("post").defer("preview")

    def changelist_view(self, request, extra_context=None):
        return super().changelist_view(request, {**(extra_context or {}), "title": "Точки на карте"})

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        return super().changeform_view(request, object_id, form_url, {
            **(extra_context or {}), "title": "Изменить точку" if object_id else "Добавить точку",
        })

    def save_model(self, request, obj, form, change):
        if not is_map_admin(request.user):
            raise PermissionDenied
        warning = update_preview(obj, form.cleaned_data.get("custom_image"))
        if warning:
            self.message_user(request, warning, messages.WARNING)
        super().save_model(request, obj, form, change)

    @admin.action(description="Обновить превью из статьи", permissions=["change"])
    def refresh_previews(self, request, queryset):
        if request.method != "POST" or not is_map_admin(request.user):
            raise PermissionDenied
        count = 0
        for marker in queryset.filter(preview_mode=MapMarker.PreviewMode.ARTICLE):
            warning = update_preview(marker)
            marker.save(update_fields=["preview", "updated_at"])
            count += 1
            if warning:
                self.message_user(request, f"{marker}: {warning}", messages.WARNING)
        self.message_user(request, f"Обновлено: {count}. Точки с режимом «Своё» пропущены.")

    def get_urls(self):
        return [path("overview/", self.admin_site.admin_view(self.overview), name="map_mapmarker_overview")] + super().get_urls()

    @method_decorator(require_GET)
    def overview(self, request):
        if not is_map_admin(request.user):
            raise PermissionDenied
        # Same search/filter semantics as the table, across all result pages.
        queryset = self.get_changelist_instance(request).queryset
        return JsonResponse([
            {"id": obj.pk, "latitude": obj.latitude, "longitude": obj.longitude, "color": obj.color,
             "title": f"{self.article(obj)} — {self.publication_status(obj)}" + ("" if obj.is_enabled else " · выключена"),
             "url": reverse("admin:map_mapmarker_change", args=[obj.pk]),
             "preview": reverse("map:preview", args=[obj.pk]) + "?v=" + str(obj.updated_at.timestamp())}
            for obj in queryset
        ], safe=False)
