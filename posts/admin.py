from django.contrib import admin

from posts.models import Post


class PostAdmin(admin.ModelAdmin):
    list_display = (
        "title", "slug", "type", "lang", "created_at",
        "published_at", "total_views",
        "is_visible"
    )
    ordering = ("-created_at",)
    readonly_fields = ("total_views",)
    exclude = ("view_count",)

    @admin.display(description="Просмотры на RU и COM")
    def total_views(self, obj):
        return obj.total_view_count


admin.site.register(Post, PostAdmin)
