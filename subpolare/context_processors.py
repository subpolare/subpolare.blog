import subpolare.strings as strings
from django.conf import settings


def settings_processor(request):
    choices = {}
    for region in ("ru", "com"):
        query = request.GET.copy()
        query.pop("_mirror_hop", None)
        query["mirror"] = region
        choices["mirror_" + region + "_link"] = request.path + "?" + query.urlencode()
    return {
        "settings": settings,
        **choices,
    }


def strings_processor(request):
    return {
        "strings": strings
    }
