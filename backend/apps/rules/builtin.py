"""Seeding the bundled merchant patterns.

The patterns live in `builtin_patterns.yaml` rather than in Python so that
adding a merchant needs no code — it is the lowest-barrier contribution in the
repository, and the one most people are equipped to make from their own
statements.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from django.db import transaction as db_transaction

from apps.accounts.models import Household
from apps.categories.models import Category
from apps.rules.models import CategoryRule

logger = logging.getLogger(__name__)

PATTERNS_FILE = Path(__file__).parent / "builtin_patterns.yaml"
PATH_SEPARATOR = ">"

__all__ = ["BuiltinPattern", "load_patterns", "seed_builtin_rules"]


@dataclass(frozen=True)
class BuiltinPattern:
    pattern: str
    category_path: tuple[str, ...]
    match_type: str

    @property
    def category_name(self) -> str:
        return self.category_path[-1]


@lru_cache(maxsize=1)
def load_patterns() -> tuple[BuiltinPattern, ...]:
    """Parse the YAML. Cached — the file never changes at runtime."""
    raw = yaml.safe_load(PATTERNS_FILE.read_text())
    entries = raw.get("patterns", []) if isinstance(raw, dict) else []

    patterns: list[BuiltinPattern] = []
    seen: set[tuple[str, str]] = set()

    for entry in entries:
        pattern = str(entry["pattern"]).strip()
        match_type = str(entry.get("match", CategoryRule.MatchType.CONTAINS)).strip()
        path = tuple(part.strip() for part in str(entry["category"]).split(PATH_SEPARATOR))

        if match_type not in CategoryRule.MatchType.values:
            raise ValueError(
                f"builtin_patterns.yaml: {pattern!r} has match: {match_type!r}, which is not "
                f"one of {CategoryRule.MatchType.values}"
            )

        key = (match_type, pattern.upper())
        if key in seen:
            raise ValueError(f"builtin_patterns.yaml: {pattern!r} is listed twice")
        seen.add(key)

        patterns.append(BuiltinPattern(pattern=pattern, category_path=path, match_type=match_type))

    return tuple(patterns)


def _category_index(household: Household) -> dict[tuple[int | None, str], Category]:
    """Every category in the household, keyed by (parent_id, name).

    Loaded once. Resolving each pattern's path with its own queries meant
    roughly 270 round trips per household — the tree is fifty rows, so reading
    it whole and walking it in memory is both simpler and far quicker.
    """
    return {
        (category.parent_id, category.name): category
        for category in Category.objects.for_household(household)
    }


def _resolve_category(
    index: dict[tuple[int | None, str], Category], path: tuple[str, ...]
) -> Category | None:
    """Walk a category path against the prefetched index.

    Returns None when the path doesn't resolve — a household that renamed or
    deleted a branch simply doesn't get those rules, rather than seeding
    failing outright.
    """
    parent_id: int | None = None
    category: Category | None = None
    for name in path:
        category = index.get((parent_id, name))
        if category is None:
            return None
        parent_id = category.pk
    return category


@db_transaction.atomic
def seed_builtin_rules(household: Household) -> int:
    """Create the bundled merchant rules for a household.

    Idempotent: skips patterns that already exist, so it doubles as the
    backfill when new merchants are added in a later release. A rule the user
    has since edited or deactivated is left exactly as they left it.

    Returns the number of rules created.
    """
    existing = {
        (match_type, pattern)
        for match_type, pattern in CategoryRule.objects.for_household(household).values_list(
            "match_type", "pattern"
        )
    }

    index = _category_index(household)
    to_create: list[CategoryRule] = []
    unresolved: list[str] = []

    for entry in load_patterns():
        pattern = entry.pattern.lower() if entry.match_type == "upi_vpa" else entry.pattern
        if (entry.match_type, pattern) in existing:
            continue

        category = _resolve_category(index, entry.category_path)
        if category is None:
            unresolved.append(" > ".join(entry.category_path))
            continue

        to_create.append(
            CategoryRule(
                household=household,
                category=category,
                pattern=pattern,
                match_type=entry.match_type,
                origin=CategoryRule.Origin.BUILTIN,
                priority=CategoryRule.DEFAULT_PRIORITY[CategoryRule.Origin.BUILTIN],
            )
        )

    if unresolved:
        logger.info(
            "Skipped %d builtin rule(s) for household %s: category path not found (%s)",
            len(unresolved),
            household.pk,
            ", ".join(sorted(set(unresolved))[:5]),
        )

    # bulk_create bypasses save(), so priority is set explicitly above and
    # patterns are pre-normalised. Validation still happened at load time.
    CategoryRule.objects.bulk_create(to_create)
    return len(to_create)
