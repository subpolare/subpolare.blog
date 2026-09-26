import re

from django import forms
from django.forms import ModelForm

from posts.models import Post


class PostEditForm(ModelForm):
    def clean_text(self):
        text = self.cleaned_data["text"]
        if re.search(r"!\[(?:Загружаю файл|Ошибка загрузки файла)\.\.\. \d+\]\(\)", text):
            raise forms.ValidationError("Дождитесь загрузки изображений или удалите отметки неудачных загрузок.")
        return text

    title = forms.CharField(
        label="Заголовок",
        required=True,
    )

    subtitle = forms.CharField(
        label="Подзаголовок",
        required=False,
    )

    image = forms.URLField(
        label="Картинка",
        required=False,
    )

    text = forms.CharField(
        label="Текст",
        min_length=0,
        max_length=100000,
        required=True,
        widget=forms.Textarea(
            attrs={
                "id": "post-editor",
            }
        ),
    )

    class Meta:
        model = Post
        fields = [
            "title",
            "subtitle",
            "image",
            "text",
        ]
