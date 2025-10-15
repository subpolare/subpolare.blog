from django.contrib import admin

from comments.models import Comment


class CommentAdmin(admin.ModelAdmin):
    list_display = (
        "author_name",
        "author",
        "created_at",
        "ipaddress",
        "text",
        "upvotes"
    )
    ordering = ("-created_at",)


admin.site.register(Comment, CommentAdmin)
