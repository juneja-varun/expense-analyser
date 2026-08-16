"""Self-hosted deployment settings.

Loaded by the Docker image. Every value that could differ between deployments
comes from the environment, so the same image serves everyone.
"""

from .base import *  # noqa: F403
from .base import BASE_DIR, TEMPLATES, env

DEBUG = False

# The compiled SPA is baked into the image and served from this same origin, so
# the session cookie is same-site in production exactly as it is behind the Vite
# dev proxy — no CORS configuration, and no cross-origin cookie behaviour that
# only shows up after deployment.
FRONTEND_DIST = BASE_DIR / "frontend_dist"
if FRONTEND_DIST.exists():
    TEMPLATES[0]["DIRS"] = [*TEMPLATES[0]["DIRS"], FRONTEND_DIST]
    STATICFILES_DIRS = [FRONTEND_DIST / "assets"]
    WHITENOISE_ROOT = FRONTEND_DIST

# No default: a deployment that forgets to set these should fail loudly at boot
# rather than run with a known-public secret key.
SECRET_KEY = env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# TLS is normally terminated by a reverse proxy in front of this container.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = env.bool("DJANGO_SECURE_COOKIES", default=True)
CSRF_COOKIE_SECURE = env.bool("DJANGO_SECURE_COOKIES", default=True)
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 30)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
