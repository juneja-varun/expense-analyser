"""Aggregations for the dashboard charts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum
from django.db.models.functions import TruncMonth

from apps.accounts.models import Household
from apps.categories.models import Category
from apps.common.dates import add_months, first_of_month
from apps.transactions.models import Transaction
from apps.transactions.services import ZERO, month_spend_by_category

__all__ = ["CategorySpend", "MonthTotals", "monthly_totals", "spend_by_category"]

UNCATEGORISED_LABEL = "Uncategorised"
UNCATEGORISED_COLOUR = "#9e9e94"


@dataclass(frozen=True)
class CategorySpend:
    category_id: int | None
    name: str
    colour: str
    amount: Decimal
    """Positive: money spent."""


@dataclass(frozen=True)
class MonthTotals:
    month: date
    spent: Decimal
    received: Decimal

    @property
    def net(self) -> Decimal:
        return self.received - self.spent


def spend_by_category(household: Household, month: date) -> list[CategorySpend]:
    """Spend for a month, rolled up to top-level categories, largest first.

    Rolls up rather than listing every leaf: forty categories make an
    unreadable chart, and "where did my money go" is a top-level question.

    Uses the same per-category figures as the budget screen
    (`transactions.services.month_spend_by_category`) so the two can never
    disagree about the same month — refunds netted off, clamped at zero.

    Income categories are excluded; uncategorised spend is shown under its own
    label, because hiding it would make the chart total disagree with the
    transaction list.
    """
    spend = month_spend_by_category(household, month, include_uncategorised=True)
    if not spend:
        return []

    categories = {
        category.pk: category
        for category in Category.objects.for_household(household).select_related("root")
    }

    totals: dict[int | None, Decimal] = {}
    for category_id, amount in spend.items():
        if amount <= ZERO:
            continue
        if category_id is None:
            totals[None] = totals.get(None, ZERO) + amount
            continue

        category = categories.get(category_id)
        if category is None or category.is_income:
            continue
        # `root` is denormalised, so rolling a third-level category up to its
        # top level needs no tree walk. A top-level category is its own root.
        key = category.root_id or category.pk
        totals[key] = totals.get(key, ZERO) + amount

    rows = [
        CategorySpend(
            category_id=key,
            name=categories[key].name if key in categories else UNCATEGORISED_LABEL,
            colour=categories[key].colour if key in categories else UNCATEGORISED_COLOUR,
            amount=amount,
        )
        for key, amount in totals.items()
        if amount > ZERO
    ]
    return sorted(rows, key=lambda row: row.amount, reverse=True)


def monthly_totals(household: Household, months: int = 12) -> list[MonthTotals]:
    """Spend and income per month, oldest first.

    Months with no activity are filled with zeroes so the chart keeps an even
    x-axis rather than silently collapsing a quiet month.
    """
    end = add_months(first_of_month(date.today()), 1)
    start = add_months(end, -months)

    rows = (
        Transaction.objects.for_household(household)
        .filter(txn_date__gte=start, txn_date__lt=end)
        .annotate(month=TruncMonth("txn_date"))
        .values("month")
        .annotate(
            spent=Sum("amount", filter=Q(amount__lt=0)),
            received=Sum("amount", filter=Q(amount__gt=0)),
        )
    )
    by_month = {row["month"]: row for row in rows}

    totals: list[MonthTotals] = []
    cursor = start
    while cursor < end:
        row = by_month.get(cursor)
        totals.append(
            MonthTotals(
                month=cursor,
                spent=abs(row["spent"]) if row and row["spent"] else ZERO,
                received=row["received"] if row and row["received"] else ZERO,
            )
        )
        cursor = add_months(cursor, 1)
    return totals
