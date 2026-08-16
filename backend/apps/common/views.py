from django.db import connection
from rest_framework import viewsets
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from apps.common.models import HouseholdScopedModel


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health(request: Request) -> Response:
    """Liveness probe used by docker-compose, CI and uptime checks."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        database_ok = True
    except Exception:
        database_ok = False

    return Response(
        {"status": "ok" if database_ok else "degraded", "database": database_ok},
        status=200 if database_ok else 503,
    )


class HouseholdScopedViewSet(viewsets.ModelViewSet):
    """Base viewset for household-owned data.

    Subclasses set `queryset` as usual; this class narrows it to the requesting
    user's households on every action. The assertion is the point: if a
    subclass overrides `get_queryset()` and forgets to scope, tests and local
    development fail immediately rather than serving another household's rows.
    """

    def get_queryset(self):
        queryset = super().get_queryset()
        model = queryset.model
        if not issubclass(model, HouseholdScopedModel):
            raise TypeError(
                f"{type(self).__name__} serves {model.__name__}, which is not a "
                "HouseholdScopedModel. Use a plain ModelViewSet, or give the model a "
                "household FK."
            )
        return queryset.for_user(self.request.user)

    def perform_create(self, serializer) -> None:
        serializer.save(household=self.request.user.default_household)
