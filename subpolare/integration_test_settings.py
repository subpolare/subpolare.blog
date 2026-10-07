"""Use only with a disposable PostgreSQL; offline tests use test_settings.py."""
import os

from .test_settings import *  # noqa: F403

DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": os.environ.get("MAP_TEST_DB", "postgres"),
    "USER": os.environ.get("MAP_TEST_USER", "maptest"),
    "PASSWORD": os.environ.get("MAP_TEST_PASSWORD", ""),
    "HOST": os.environ.get("MAP_TEST_HOST", "127.0.0.1"),
    "PORT": os.environ.get("MAP_TEST_PORT", "55439"),
    "TEST": {"NAME": "test_subpolare_map"},
}}
