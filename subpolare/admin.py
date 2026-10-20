from django.contrib.admin import AdminSite
from django.contrib.admin.apps import AdminConfig


class BlogAdminSite(AdminSite):
    def get_app_list(self, request, app_label=None):
        apps = super().get_app_list(request, app_label)
        # Hide navigation entries only; keep registered models and direct URLs.
        if app_label is None:
            apps = [app for app in apps if app["app_label"] in {"map", "posts"}]
        return apps


class BlogAdminConfig(AdminConfig):
    default_site = "subpolare.admin.BlogAdminSite"
