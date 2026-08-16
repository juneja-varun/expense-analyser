"""Category operations that span more than one model instance."""

from __future__ import annotations

from django.db import transaction

from apps.accounts.models import Household
from apps.categories.models import Category
from apps.categories.taxonomy import (
    DEFAULT_TAXONOMY,
    INCOME_TAXONOMY,
    UNCATEGORISED_NAME,
)

__all__ = ["get_uncategorised", "seed_default_categories"]


@transaction.atomic
def seed_default_categories(household: Household) -> int:
    """Create the starting category tree for a household.

    Idempotent: skips any top-level category that already exists, so it is safe
    to re-run after adding categories to the taxonomy in a later release
    without disturbing what the user has renamed or added.

    Returns the number of categories created.
    """
    created = 0
    sort_order = 0

    for group, is_income in ((DEFAULT_TAXONOMY, False), (INCOME_TAXONOMY, True)):
        for name, colour, children in group:
            sort_order += 1

            root, was_created = Category.objects.get_or_create(
                household=household,
                name=name,
                parent=None,
                defaults={
                    "colour": colour,
                    "is_income": is_income,
                    "is_system": True,
                    "sort_order": sort_order,
                },
            )
            if not was_created:
                # The user already has this branch; leave their edits alone.
                continue
            created += 1

            for child_order, (child_name, grandchildren) in enumerate(children, start=1):
                child = Category.objects.create(
                    household=household,
                    name=child_name,
                    parent=root,
                    colour=colour,
                    is_income=is_income,
                    is_system=True,
                    sort_order=child_order,
                )
                created += 1

                for grandchild_order, grandchild_name in enumerate(grandchildren, start=1):
                    Category.objects.create(
                        household=household,
                        name=grandchild_name,
                        parent=child,
                        colour=colour,
                        is_income=is_income,
                        is_system=True,
                        sort_order=grandchild_order,
                    )
                    created += 1

    return created


def get_uncategorised(household: Household) -> Category:
    """The fallback category for transactions no rule matched.

    Created on demand so an older household that predates seeding, or one whose
    owner deleted it, still has somewhere to put unmatched transactions.
    """
    category, _ = Category.objects.get_or_create(
        household=household,
        name=UNCATEGORISED_NAME,
        parent=None,
        defaults={"colour": "#9e9e94", "is_system": True, "sort_order": 999},
    )
    return category
