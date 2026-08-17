from __future__ import annotations

from decimal import Decimal

from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from apps.budgets.views import parse_month
from apps.insights import services

MAX_TREND_MONTHS = 36
ZERO = Decimal("0.00")


class InsightsViewSet(ViewSet):
    """Read-only aggregations for the dashboard.

    A plain `ViewSet` rather than `HouseholdScopedViewSet`: there is no
    queryset to scope, and each action reads the household off the request and
    passes it explicitly to a service that scopes its own queries.
    """

    @action(detail=False, methods=["get"])
    def spend_by_category(self, request: Request) -> Response:
        """Where a month's money went, rolled up to top-level categories."""
        month = parse_month(request.query_params.get("month"))
        rows = services.spend_by_category(request.user.default_household, month)

        return Response(
            {
                "month": month.isoformat(),
                "total": str(sum((row.amount for row in rows), start=ZERO)),
                "categories": [
                    {
                        "category": row.category_id,
                        "name": row.name,
                        "colour": row.colour,
                        "amount": str(row.amount),
                    }
                    for row in rows
                ],
            }
        )

    @action(detail=False, methods=["get"])
    def monthly_trend(self, request: Request) -> Response:
        """Spend and income per month, oldest first."""
        try:
            months = int(request.query_params.get("months", 12))
        except (TypeError, ValueError):
            months = 12
        months = max(1, min(months, MAX_TREND_MONTHS))

        return Response(
            {
                "months": [
                    {
                        "month": row.month.isoformat(),
                        "spent": str(row.spent),
                        "received": str(row.received),
                        "net": str(row.net),
                    }
                    for row in services.monthly_totals(request.user.default_household, months)
                ]
            }
        )
