import subpolare.strings as strings
from django.conf import settings


def settings_processor(request):
    return {
        "settings": settings
    }


def strings_processor(request):
    return {
        "strings": strings
    }
