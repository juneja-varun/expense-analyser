"""Test settings — fast, hermetic, no reliance on a developer's .env."""

from .base import *  # noqa: F403
from .base import DATABASES, MIDDLEWARE, STORAGES, env

DEBUG = False
SECRET_KEY = "test-key-not-secret"

# Static file serving is a deployment concern; skip it so tests don't depend on
# a collectstatic run having happened.
MIDDLEWARE = [m for m in MIDDLEWARE if "whitenoise" not in m]
STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}

DATABASES["default"] = env.db(
    "TEST_DATABASE_URL",
    default="postgres://localhost:5432/expense_analyser_test",
)
DATABASES["default"]["ATOMIC_REQUESTS"] = True

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
