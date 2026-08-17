from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.common.models import HouseholdScopedModel


def first_of_month(value: date) -> date:
    """Normalise any date to the first of its month.

    Budgets are monthly, so the day is noise. Storing a real `DateField` rather
    than a year/month pair keeps ordering, range filters and `__gte` lookups
    working without special cases.
    """
    return value.replace(day=1)


def add_months(value: date, months: int) -> date:
    """Shift a date by whole months, from the first of the month.

    Hand-rolled rather than pulling in `python-dateutil`: budgets only ever
    move between month boundaries, so the general case (what is 31 January plus
    one month?) never arises here.
    """
    zero_based = value.month - 1 + months
    year = value.year + zero_based // 12
    month = zero_based % 12 + 1
    return date(year, month, 1)


class Budget(HouseholdScopedModel):
    """A spending limit for one category in one month.

    Set on any level of the tree. A budget on "Food & Dining" covers everything
    beneath it, because that is what a person means when they budget a top-level
    category — see `apps.budgets.services.budget_progress`.
    """

    category = models.ForeignKey(
        "categories.Category",
        on_delete=models.CASCADE,
        related_name="budgets",
    )
    month = models.DateField(help_text="Any date in the month; stored as the 1st.")
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="The limit for this category this month, as a positive number.",
    )
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-month", "category__sort_order", "category__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["household", "category", "month"],
                name="unique_budget_per_category_month",
            ),
        ]
        indexes = [models.Index(fields=["household", "month"])]

    def __str__(self) -> str:
        return f"{self.category} — {self.month:%b %Y}: {self.amount}"

    def clean(self) -> None:
        if self.category_id:
            if self.category.household_id != self.household_id:
                raise ValidationError({"category": "Category belongs to a different household."})
            if self.category.is_income:
                raise ValidationError(
                    {
                        "category": (
                            "Income categories can't be budgeted — a budget is a cap on "
                            "spending, and capping what you earn isn't meaningful."
                        )
                    }
                )
        if self.amount is not None and self.amount < 0:
            raise ValidationError({"amount": "A budget cannot be negative."})

    def save(self, *args, **kwargs) -> None:
        if self.month:
            self.month = first_of_month(self.month)
        self.clean()
        super().save(*args, **kwargs)
