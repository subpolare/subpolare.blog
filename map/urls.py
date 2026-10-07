from django.urls import path

from . import views

app_name = "map"
urlpatterns = [
    path("markers/", views.markers, name="markers"),
    path("previews/<int:marker_id>/", views.preview, name="preview"),
]
