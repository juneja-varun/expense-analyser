"""Month arithmetic.

Budgets, insights and any future reporting all slice by calendar month, so the
helpers live here rather than in whichever app happened to need them first.
"""

from __future__ import annotations

from datetime import date

__all__ = ["add_months", "first_of_month", "month_range"]


def first_of_month(value: date) -> date:
    """Normalise any date to the first of its month."""
    return value.replace(day=1)


def add_months(value: date, months: int) -> date:
    """Shift a date by whole months, returning the first of the result.

    Hand-rolled rather than pulling in `python-dateutil`: everything here moves
    between month boundaries, so the ambiguous case (what is 31 January plus
    one month?) never arises.
    """
    zero_based = value.month - 1 + months
    year = value.year + zero_based // 12
    month = zero_based % 12 + 1
    return date(year, month, 1)


def month_range(value: date) -> tuple[date, date]:
    """Half-open `[start, end)` covering the month containing `value`.

    Half-open so date filters need no "last day of month" arithmetic and no
    `__lte` off-by-one.
    """
    start = first_of_month(value)
    return start, add_months(start, 1)
