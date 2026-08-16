from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import TemplateView

from apps.common.views import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/auth/", include("apps.accounts.urls")),
]

# In production the compiled SPA is served from this same origin. Any path that
# is not an API or admin route hands back index.html so client-side routing
# works on a hard refresh. In development Vite serves the SPA instead, so this
# is skipped and an unknown path correctly 404s.
if getattr(settings, "FRONTEND_DIST", None) and settings.FRONTEND_DIST.exists():
    urlpatterns += [
        re_path(
            r"^(?!api/|admin/|static/).*$",
            TemplateView.as_view(template_name="index.html"),
            name="spa",
        ),
    ]
