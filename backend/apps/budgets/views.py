from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from apps.budgets.models import Budget, add_months, first_of_month
from apps.budgets.services import budget_progress
from apps.common.views import HouseholdScopedViewSet


def parse_month(value: str | None) -> date:
    """`?month=YYYY-MM`, defaulting to the current month."""
    if not value:
        return first_of_month(date.today())
    for fmt in ("%Y-%m", "%Y-%m-%d"):
        try:
            return first_of_month(datetime.strptime(value, fmt).date())
        except ValueError:
            continue
    raise ValidationError({"month": "Use YYYY-MM, e.g. 2024-04."})


class BudgetSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.full_name", read_only=True, default=None)
    category_colour = serializers.CharField(source="category.colour", read_only=True, default=None)

    class Meta:
        model = Budget
        fields = [
            "id",
            "category",
            "category_name",
            "category_colour",
            "month",
            "amount",
            "note",
        ]

    def validate_category(self, category):
        household = self.context["request"].user.default_household
        if category.household_id != household.pk:
            raise serializers.ValidationError("That category belongs to another household.")
        if category.is_income:
            raise serializers.ValidationError(
                "Income categories can't be budgeted — a budget caps spending."
            )
        return category

    def validate_month(self, month: date) -> date:
        return first_of_month(month)


class BudgetViewSet(HouseholdScopedViewSet):
    """Monthly spending limits per category."""

    serializer_class = BudgetSerializer
    queryset = Budget.objects.select_related(
        "category", "category__parent", "category__parent__parent"
    )

    def get_queryset(self):
        queryset = super().get_queryset()
        if month := self.request.query_params.get("month"):
            queryset = queryset.filter(month=parse_month(month))
        return queryset

    @action(detail=False, methods=["get"])
    def progress(self, request: Request) -> Response:
        """Budget versus actual for a month, most over-budget first."""
        month = parse_month(request.query_params.get("month"))
        rows = budget_progress(request.user.default_household, month)

        return Response(
            {
                "month": month.isoformat(),
                "total_budgeted": str(sum((r.budgeted for r in rows), start=Decimal("0.00"))),
                "total_spent": str(sum((r.spent for r in rows), start=Decimal("0.00"))),
                "categories": [
                    {
                        "category": row.category_id,
                        "category_name": row.category_name,
                        "category_colour": row.category_colour,
                        "budgeted": str(row.budgeted),
                        "spent": str(row.spent),
                        "remaining": str(row.remaining),
                        "percent_used": row.percent_used,
                        "is_over": row.is_over,
                    }
                    for row in rows
                ],
            }
        )

    @action(detail=False, methods=["post"])
    def copy_from_previous_month(self, request: Request) -> Response:
        """Duplicate last month's budgets into this one.

        Budgets are mostly stable month to month, so re-entering a dozen
        numbers every month is the kind of chore that makes people abandon
        budgeting entirely. Existing budgets are left alone rather than
        overwritten.
        """
        month = parse_month(request.data.get("month"))
        household = request.user.default_household
        previous = add_months(month, -1)

        already_set = set(
            Budget.objects.for_household(household)
            .filter(month=month)
            .values_list("category_id", flat=True)
        )
        source_budgets = Budget.objects.for_household(household).filter(month=previous)

        created = Budget.objects.bulk_create(
            [
                Budget(
                    household=household,
                    category_id=budget.category_id,
                    month=month,
                    amount=budget.amount,
                    note=budget.note,
                )
                for budget in source_budgets
                if budget.category_id not in already_set
            ]
        )

        return Response(
            {
                "month": month.isoformat(),
                "copied_from": previous.isoformat(),
                "created": len(created),
                "skipped_existing": len(already_set),
            }
        )
