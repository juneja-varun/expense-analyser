"""Budget versus actual spend."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from apps.accounts.models import Household
from apps.budgets.models import Budget
from apps.categories.models import Category
from apps.common.dates import first_of_month
from apps.transactions.services import ZERO, month_spend_by_category

__all__ = ["BudgetProgress", "budget_progress", "descendant_ids"]


@dataclass(frozen=True)
class BudgetProgress:
    category_id: int
    category_name: str
    category_colour: str
    budgeted: Decimal
    spent: Decimal

    @property
    def remaining(self) -> Decimal:
        return self.budgeted - self.spent

    @property
    def is_over(self) -> bool:
        return self.spent > self.budgeted

    @property
    def percent_used(self) -> int:
        """Whole percent, uncapped — going over should be visible, not clipped.

        Rounded half *up* rather than with `Decimal`'s default banker's
        rounding, which would show 450 of 2000 (22.5%) as 22% and quietly
        understate how much of a budget is gone.
        """
        if self.budgeted == ZERO:
            return 0
        used = self.spent / self.budgeted * 100
        return int(used.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def descendant_ids(household: Household) -> dict[int, set[int]]:
    """For each category, itself plus every category beneath it.

    Built from one query. Budgeting a parent has to cover its children — a
    person who budgets "Food & Dining" means the whole branch, not the handful
    of transactions filed directly on the parent.
    """
    categories = list(Category.objects.for_household(household).values("id", "parent_id"))
    children: dict[int | None, list[int]] = defaultdict(list)
    for category in categories:
        children[category["parent_id"]].append(category["id"])

    def collect(category_id: int) -> set[int]:
        found = {category_id}
        for child_id in children.get(category_id, []):
            found |= collect(child_id)
        return found

    return {category["id"]: collect(category["id"]) for category in categories}


def budget_progress(household: Household, month: date) -> list[BudgetProgress]:
    """Every budget for the month, with how much of it has been spent.

    Three queries regardless of how many budgets exist: the budgets, the
    month's spend grouped by category, and the category tree.
    """
    start = first_of_month(month)

    budgets = list(
        Budget.objects.for_household(household)
        .filter(month=start)
        .select_related("category", "category__parent", "category__parent__parent")
    )
    if not budgets:
        return []

    spend = month_spend_by_category(household, start)
    descendants = descendant_ids(household)

    progress = [
        BudgetProgress(
            category_id=budget.category_id,
            category_name=budget.category.full_name,
            category_colour=budget.category.colour,
            budgeted=budget.amount,
            spent=sum(
                (spend.get(cid, ZERO) for cid in descendants.get(budget.category_id, set())),
                ZERO,
            ),
        )
        for budget in budgets
    ]

    # Most over-budget first: that is what a person opens this screen to find.
    return sorted(progress, key=lambda p: p.spent - p.budgeted, reverse=True)
