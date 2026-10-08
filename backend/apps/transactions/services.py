"""Transaction aggregations.

`month_spend_by_category` lives here, rather than in budgets or insights,
because both of those need it and they must never disagree. Two definitions of
"what did I spend on food in April" is the kind of inconsistency that makes a
finance app untrustworthy.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum

from apps.accounts.models import Household
from apps.common.dates import month_range
from apps.transactions.models import Transaction

__all__ = ["ZERO", "month_spend_by_category"]

ZERO = Decimal("0.00")


def month_spend_by_category(
    household: Household, month: date, *, include_uncategorised: bool = False
) -> dict[int | None, Decimal]:
    """Spend per category for a month, as positive numbers.

    Refunds are **netted off** rather than ignored: ₹450 of food with ₹150
    refunded is ₹300 spent, and that is what both the budget screen and the
    spend chart should say.

    Clamped at zero per category — a category that netted positive over the
    month has not "spent negative money", and letting it go negative would
    quietly offset real spending elsewhere in a roll-up.

    Keyed by category id; `None` is uncategorised spend, included only when
    asked for.

    Uncategorised is deliberately **not** netted. It is not a category but a
    pile of things the rules could not place, so a credit in it has nothing to
    do with the debits — a salary landing there does not offset a month of
    shopping. Netting them cancelled ₹1.3L of real spending against one
    uncategorised salary credit and dropped the bucket from the chart
    entirely, so the chart said ₹19k against ₹1.5L actually spent.
    """
    start, end = month_range(month)

    queryset = Transaction.objects.for_household(household).filter(
        txn_date__gte=start, txn_date__lt=end
    )
    if not include_uncategorised:
        queryset = queryset.filter(category__isnull=False)

    rows = queryset.values("category_id").annotate(
        total=Sum("amount"),
        debits=Sum("amount", filter=Q(amount__lt=0)),
    )

    spend: dict[int | None, Decimal] = {}
    for row in rows:
        # Amounts are signed with debits negative, so flip to get spend.
        total = row["debits"] if row["category_id"] is None else row["total"]
        spend[row["category_id"]] = max(-(total or ZERO), ZERO)
    return spend
