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

    Inserts one level at a time with `bulk_create` — the tree is around fifty
    rows, and creating them individually made registration a fifty-query
    operation. `bulk_create` bypasses `save()`, so `depth` and `root` are set
    explicitly here; the tests in test_seeding.py check they still come out
    right.

    Returns the number of categories created.
    """
    existing_roots = set(
        Category.objects.for_household(household)
        .filter(parent__isnull=True)
        .values_list("name", flat=True)
    )

    roots: list[Category] = []
    # Children are held with a reference to their parent's *spec* until the
    # parents have primary keys.
    pending_children: list[tuple[str, list[str], str, bool, int, Category]] = []
    sort_order = 0

    for group, is_income in ((DEFAULT_TAXONOMY, False), (INCOME_TAXONOMY, True)):
        for name, colour, children in group:
            sort_order += 1
            if name in existing_roots:
                # The user already has this branch; leave their edits alone.
                continue

            root = Category(
                household=household,
                name=name,
                parent=None,
                depth=0,
                root=None,
                colour=colour,
                is_income=is_income,
                is_system=True,
                sort_order=sort_order,
            )
            roots.append(root)
            for child_order, (child_name, grandchildren) in enumerate(children, start=1):
                pending_children.append(
                    (child_name, grandchildren, colour, is_income, child_order, root)
                )

    if not roots:
        return 0

    Category.objects.bulk_create(roots)

    children: list[Category] = []
    pending_grandchildren: list[tuple[str, str, bool, int, Category]] = []

    for name, grandchildren, colour, is_income, order, root in pending_children:
        child = Category(
            household=household,
            name=name,
            parent=root,
            depth=1,
            root=root,
            colour=colour,
            is_income=is_income,
            is_system=True,
            sort_order=order,
        )
        children.append(child)
        for grandchild_order, grandchild_name in enumerate(grandchildren, start=1):
            pending_grandchildren.append(
                (grandchild_name, colour, is_income, grandchild_order, child)
            )

    Category.objects.bulk_create(children)

    grandchildren_rows = [
        Category(
            household=household,
            name=name,
            parent=parent,
            depth=2,
            # The denormalisation that makes roll-ups a single join: a
            # third-level category points at the *top* level, not its parent.
            root=parent.root,
            colour=colour,
            is_income=is_income,
            is_system=True,
            sort_order=order,
        )
        for name, colour, is_income, order, parent in pending_grandchildren
    ]
    Category.objects.bulk_create(grandchildren_rows)

    return len(roots) + len(children) + len(grandchildren_rows)


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
