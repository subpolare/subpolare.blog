"""Offline tests: no database, external services, credentials or debug toolbar."""
import os

os.environ["DEBUG"] = "false"
os.environ["SENTRY_DSN"] = ""

from .settings import *  # noqa: E402,F403

SECRET_KEY = "offline-tests-only"
DATABASES = {"default": {"ENGINE": "django.db.backends.dummy"}}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
PEPIC_UPLOAD_URL = ""
PEPIC_UPLOAD_CODE = ""
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
LOGGING = {"version": 1, "disable_existing_loggers": True}
