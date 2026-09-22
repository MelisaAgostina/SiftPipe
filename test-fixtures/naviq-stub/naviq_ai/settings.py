"""
Minimal settings for the stub NaViQ target - see test-fixtures/naviq-stub/README.md.

docker/naviq/siftpipe_settings.py imports this module (NAVIQ_BASE_SETTINGS
defaults to "naviq_ai.settings") and layers ALLOWED_HOSTS += ["naviq"] on top,
so this only needs to be a real, working Django settings module - nothing here
needs to match real NaViQ's actual settings beyond that contract.
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Fine for a throwaway CI fixture DB - never used for anything real.
SECRET_KEY = "naviq-stub-fixture-not-a-real-secret"

DEBUG = True

# siftpipe_settings.py additionally appends "naviq" (the container's hostname
# on app-net). "localhost" is needed here directly: docker/naviq/Dockerfile's
# own HEALTHCHECK curls http://localhost:8001/ from inside the container -
# real bug hit live testing this fixture (2026-09-22), same ALLOWED_HOSTS
# class of bug SESSION notes already record against real NaViQ.
ALLOWED_HOSTS = ["localhost"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "naviq_ai.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "naviq_ai.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SITE_ID = 1
