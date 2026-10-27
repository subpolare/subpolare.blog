import os
from pathlib import Path
from random import randint

import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from django.utils.translation import gettext_lazy as _

# Build paths inside the project like this: BASE_DIR / "subdir".
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv("SECRET_KEY") or "wow so secret"
DEBUG = (os.getenv("DEBUG") != "false")

ALLOWED_HOSTS = [
    "0.0.0.0",
    "127.0.0.1",
    "localhost",
    "subpolare.ru",
    ".subpolare.ru",
    "subpolare.com",
    "www.subpolare.com",
]
INTERNAL_IPS = ["127.0.0.1"]

ADMINS = [
    ("subpolare", "me@subpolare.ru"),
]


# Application definition

INSTALLED_APPS = [
    "subpolare.admin.BlogAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.sitemaps",
    "users.apps.UsersConfig",
    "posts.apps.PostsConfig",
    "comments.apps.CommentsConfig",  # Migration history only; no runtime models.
    "rss.apps.RssConfig",
    "clickers.apps.ClickersConfig",
    "map.apps.MapConfig",
    "mirrors.apps.MirrorsConfig",
]

MIDDLEWARE = [
    "mirrors.middleware.MirrorMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "subpolare.middleware.DomainLocaleMiddleware",
    "subpolare.middleware.RequestLoggingMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "subpolare.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            BASE_DIR / "frontend/html",
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
                "django.contrib.auth.context_processors.auth",
                "subpolare.context_processors.settings_processor",
                "subpolare.context_processors.strings_processor",
            ],
        },
    },
]

WSGI_APPLICATION = "subpolare.wsgi.application"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler"
        },
    },
    "loggers": {
        "": {  # "catch all" loggers by referencing it with the empty string
            "handlers": ["console"],
            "level": "DEBUG",
        },
    },
}

# Database
# https://docs.djangoproject.com/en/4.1/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": os.getenv("POSTGRES_DB") or "subpolare",
        "USER": os.getenv("POSTGRES_USER") or "postgres",
        "PASSWORD": os.getenv("POSTGRES_PASSWORD") or "",
        "HOST": os.getenv("POSTGRES_HOST") or "localhost",
        "PORT": os.getenv("POSTGRES_PORT") or 5432,
    }
}

# Password validation
# https://docs.djangoproject.com/en/4.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = []


# Internationalization
# https://docs.djangoproject.com/en/4.1/topics/i18n/

LANGUAGES = [
    ("en", "English"),
    ("ru", "Russian"),
    ("es", "Español"),
    ("zh", "Chinese"),
    ("hi", "Hindi"),
]

LANGUAGE_CODE = "ru"
TIME_ZONE = "UTC"
USE_I18N = True
USE_L10N = True
USE_TZ = False

LOCALE_PATHS = [
    os.path.join(BASE_DIR, "locale"),
]

# Domain to language mapping
DOMAIN_LANGUAGES = {
    "subpolare.com": "ru",
    "www.subpolare.com": "ru",
    "subpolare.ru": "ru",
    "en.subpolare.ru": "en",
    "es.subpolare.ru": "es",
    "zh.subpolare.ru": "zh",
    "hi.subpolare.ru": "hi",
}

if DEBUG:
    DOMAIN_LANGUAGES = {
        "localhost": "ru",
        "127.0.0.1": "ru",
        **DOMAIN_LANGUAGES,
    }

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.1/howto/static-files/

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "tmp/static"

STATICFILES_DIRS = [
    BASE_DIR / "frontend/static",
]

# Default primary key field type
# https://docs.djangoproject.com/en/4.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Auth

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# RSS is retained but disabled until explicitly enabled.
RSS_ENABLED = os.getenv("RSS_ENABLED", "false").lower() == "true"

# App specific

# Server-only Pepic credentials. Never include the code in templates or JS.
PEPIC_UPLOAD_URL = os.getenv("PEPIC_UPLOAD_URL", "")
PEPIC_UPLOAD_CODE = os.getenv("PEPIC_UPLOAD_CODE", "")
PEPIC_MEDIA_ORIGIN = os.getenv("PEPIC_MEDIA_ORIGIN", "https://media.subpolare.ru").rstrip("/")
PEPIC_STORAGE_ROOT = os.getenv("PEPIC_STORAGE_ROOT", "")

MAP_IMAGE_ALLOWED_HOSTS = [host.strip().lower() for host in os.getenv("MAP_IMAGE_ALLOWED_HOSTS", "i.subpolare.ru").split(",") if host.strip()]

AUTH_USER_MODEL = "users.User"

SESSION_COOKIE_AGE = 300 * 24 * 60 * 60  # 300 days
SENTRY_DSN = os.getenv("SENTRY_DSN")

APP_HOST = "subpolare.ru"

CSRF_TRUSTED_ORIGINS = [
    "https://subpolare.com",
    "https://www.subpolare.com",
    "https://subpolare.ru",
    "https://*.subpolare.ru",
]

STYLES_HASH = os.getenv("GITHUB_SHA") or str(randint(1, 10000))

SITE_REGION = os.getenv("SITE_REGION", "ru")
MIRROR_RUNTIME = os.getenv("MIRROR_RUNTIME", "/mirror-runtime")
GEO_REDIRECT_ENABLED = os.getenv("GEO_REDIRECT_ENABLED", "false").lower() == "true"
MIRROR_SIGNING_KEY = os.getenv("MIRROR_SIGNING_KEY", SECRET_KEY)


if SENTRY_DSN and not DEBUG:
    # activate sentry on production
    sentry_sdk.init(dsn=SENTRY_DSN, integrations=[
        DjangoIntegration(),
    ])

if DEBUG:
    INSTALLED_APPS += ["debug_toolbar"]
    MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware"] + MIDDLEWARE
