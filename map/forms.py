from django import forms
from django.utils import timezone

from posts.models import Post
from .models import MapMarker


class PostChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, post):
        status = "закрытая" if post.is_members_only else "опубликована" if post.is_visible and post.published_at <= timezone.now() else "черновик / запланирована"
        return f"{post.title or post.slug} — {post.lang} · {post.slug} ({status})"


class MapMarkerForm(forms.ModelForm):
    post = PostChoiceField(queryset=Post.objects.order_by("-published_at"), label="Статья")
    custom_image = forms.FileField(
        label="Своя картинка", required=False,
        help_text="JPEG, PNG, WebP или GIF до 8 МиБ и 24 Мп. Сохраняется только квадрат 128×128; при ошибке — заглушка.",
        widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp,image/gif"}),
    )

    class Meta:
        model = MapMarker
        fields = ("post", "latitude", "longitude", "color", "is_enabled", "preview_mode", "custom_image")
        widgets = {
            "color": forms.TextInput(attrs={"type": "color"}),
            "latitude": forms.NumberInput(attrs={"step": "any", "min": -90, "max": 90}),
            "longitude": forms.NumberInput(attrs={"step": "any", "min": -180, "max": 180}),
        }

    def clean(self):
        data = super().clean()
        if data.get("custom_image") and data.get("preview_mode") != MapMarker.PreviewMode.CUSTOM:
            self.add_error("preview_mode", "Выберите «Своё», чтобы использовать загруженную картинку.")
        return data
