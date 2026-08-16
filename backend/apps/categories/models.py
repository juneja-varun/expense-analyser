from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from apps.common.models import HouseholdScopedModel

MAX_DEPTH = 2
"""Zero-indexed: 0 = top level, 2 = sub-sub-category. Three levels total."""


class Category(HouseholdScopedModel):
    """A spending category, in a tree at most three levels deep.

    Modelled as a self-referential FK with a denormalised `root` rather than
    with django-mptt or treebeard. The tree is small and fixed-depth, so a
    materialised `root_id` turns "total spend per top-level category" into one
    indexed join — no tree-rebuild step, and one fewer dependency for a
    contributor to learn.
    """

    name = models.CharField(max_length=100)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
    )
    root = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="descendants",
        editable=False,
        help_text="Top-level ancestor. Denormalised so roll-ups are a single join.",
    )
    depth = models.PositiveSmallIntegerField(default=0, editable=False)

    colour = models.CharField(
        max_length=7,
        blank=True,
        help_text="Hex colour for charts, e.g. #1f6f4a.",
    )
    icon = models.CharField(max_length=40, blank=True)
    is_income = models.BooleanField(
        default=False,
        help_text="Income rather than spending. Kept out of expense totals and budgets.",
    )
    is_system = models.BooleanField(
        default=False,
        help_text="Seeded by the app. Users may rename these but not delete them.",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["household", "parent", "name"],
                name="unique_category_name_per_parent",
            ),
            models.UniqueConstraint(
                fields=["household", "name"],
                condition=models.Q(parent__isnull=True),
                name="unique_root_category_name",
            ),
        ]
        indexes = [
            models.Index(fields=["household", "root"]),
            models.Index(fields=["household", "parent"]),
        ]

    def __str__(self) -> str:
        return self.full_name

    @property
    def full_name(self) -> str:
        """Breadcrumb path, e.g. "Food & Dining → Eating Out".

        Walks iteratively with a hard bound rather than recursing: a cycle is
        prevented on save, but this is also called on unsaved in-memory
        instances (including by `__str__` in a traceback), where one may exist.
        """
        names = [self.name]
        node = self
        for _ in range(MAX_DEPTH + 1):
            if node.parent_id is None:
                break
            node = node.parent
            names.append(node.name)
        return " → ".join(reversed(names))

    def clean(self) -> None:
        if self.parent_id is None:
            return

        if self.parent_id == self.pk:
            raise ValidationError({"parent": "A category cannot be its own parent."})

        if self.parent.household_id != self.household_id:
            raise ValidationError({"parent": "Parent belongs to a different household."})

        if self.parent.depth >= MAX_DEPTH:
            raise ValidationError(
                {
                    "parent": (
                        f"Categories nest at most {MAX_DEPTH + 1} levels deep "
                        f"({self.parent.full_name} is already at the deepest level)."
                    )
                }
            )

        # Walk up to catch a cycle created by re-parenting an existing subtree.
        ancestor = self.parent
        while ancestor is not None:
            if ancestor.pk == self.pk:
                raise ValidationError({"parent": "That would create a loop in the tree."})
            ancestor = ancestor.parent

    def save(self, *args, **kwargs) -> None:
        # `clean()` is called explicitly: Django does not run it on save(), and
        # the depth and household rules are invariants rather than form-level
        # niceties — a violation should never reach the database, whether it
        # came from the API, the admin, a shell or a fixture.
        self.clean()
        self._denormalise()
        super().save(*args, **kwargs)

    def _denormalise(self) -> None:
        """Keep `depth` and `root` consistent with `parent`.

        Derived on save rather than trusted from the caller, for the same
        reason.
        """
        if self.parent_id is None:
            self.depth = 0
            self.root = None
        else:
            self.depth = self.parent.depth + 1
            self.root = self.parent.root or self.parent

    @property
    def effective_root(self) -> Category:
        """The top-level category this one rolls up into (itself, if top level)."""
        return self.root or self
