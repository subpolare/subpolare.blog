from django.contrib import admin

from posts.models import Post


class PostAdmin(admin.ModelAdmin):
    list_display = (
        "title", "slug", "type", "lang", "created_at",
        "published_at", "local_views",
        "is_visible"
    )
    ordering = ("-created_at",)
    readonly_fields = ("local_views",)
    exclude = ("view_count",)

    @admin.display(description="Просмотры на этом сервере")
    def local_views(self, obj):
        return obj.local_view_count


admin.site.register(Post, PostAdmin)
