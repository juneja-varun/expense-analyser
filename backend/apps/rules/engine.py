"""Applying categorisation rules to transactions.

First match wins, in this order:

1. Rules the user wrote
2. Rules learned from their past recategorisations
3. Rules shipped with the app

That order falls out of `CategoryRule.DEFAULT_PRIORITY`, so the engine only has
to respect `-priority`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from django.db import transaction as db_transaction
from django.db.models import F

from apps.accounts.models import Household
from apps.categories.models import Category
from apps.rules.models import CategoryRule, extract_vpa, normalise_for_matching
from apps.transactions.models import Transaction

__all__ = [
    "CategorisationResult",
    "categorise",
    "categorise_transactions",
    "learn_from_recategorisation",
]


@dataclass(frozen=True)
class CategorisationResult:
    categorised: int
    unmatched: int
    skipped_user_categorised: int

    @property
    def total(self) -> int:
        return self.categorised + self.unmatched + self.skipped_user_categorised


def active_rules(household: Household) -> list[CategoryRule]:
    """Every active rule for a household, best first.

    Loaded once and matched in Python rather than queried per transaction: a
    household has tens of rules and an import has hundreds of transactions, so
    one query beats N.
    """
    return list(
        CategoryRule.objects.for_household(household)
        .filter(is_active=True)
        .select_related("category")
        .order_by("-priority", "id")
    )


def categorise(description: str, rules: Sequence[CategoryRule]) -> CategoryRule | None:
    """The first rule matching this description, or None.

    `rules` must already be ordered by precedence — see `active_rules`.
    """
    for rule in rules:
        if rule.matches(description):
            return rule
    return None


@db_transaction.atomic
def categorise_transactions(
    household: Household,
    transactions: Iterable[Transaction] | None = None,
    *,
    include_user_categorised: bool = False,
) -> CategorisationResult:
    """Apply the household's rules to its transactions.

    By default this never touches a transaction a person categorised by hand.
    Silently overwriting a deliberate choice — on every subsequent import, no
    less — would make the app feel broken. Pass `include_user_categorised=True`
    only for an explicit "re-run everything" action the user asked for.
    """
    rules = active_rules(household)

    # Deliberately not filtered in SQL: user-categorised rows are skipped in
    # the loop below so the result can report how many were protected. A count
    # of zero would otherwise be indistinguishable from "there were none".
    if transactions is None:
        candidates = list(Transaction.objects.for_household(household))
    else:
        candidates = list(transactions)

    categorised = 0
    unmatched = 0
    skipped = 0
    to_update: list[Transaction] = []
    match_counts: dict[int, int] = {}

    for txn in candidates:
        if txn.is_categorised_by_user and not include_user_categorised:
            skipped += 1
            continue

        rule = categorise(txn.description, rules) if rules else None
        if rule is None:
            unmatched += 1
            continue

        if txn.category_id != rule.category_id:
            txn.category_id = rule.category_id
            to_update.append(txn)
        categorised += 1
        match_counts[rule.pk] = match_counts.get(rule.pk, 0) + 1

    if to_update:
        Transaction.objects.bulk_update(to_update, ["category"])

    # Bumped per rule rather than per transaction, so a large import costs a
    # handful of queries instead of one per row.
    for rule_id, count in match_counts.items():
        CategoryRule.objects.filter(pk=rule_id).update(match_count=F("match_count") + count)

    return CategorisationResult(
        categorised=categorised,
        unmatched=unmatched,
        skipped_user_categorised=skipped,
    )


def learn_from_recategorisation(
    transaction: Transaction, category: Category
) -> CategoryRule | None:
    """Turn a manual recategorisation into a rule.

    This is what makes the app improve with use and no AI involved: correct a
    merchant once, and every future statement files it correctly.

    Prefers the UPI VPA when the narration has one — it is the only part of an
    Indian UPI string that stays constant for a merchant across banks and
    months. Falls back to the most distinctive word in the description.

    Returns None when nothing reliable can be extracted: a bad rule that
    mis-files future transactions is worse than no rule at all.
    """
    vpa = extract_vpa(transaction.description)
    if vpa:
        match_type, pattern = CategoryRule.MatchType.UPI_VPA, vpa
    else:
        fragment = distinctive_fragment(transaction.description)
        if fragment is None:
            return None
        match_type, pattern = CategoryRule.MatchType.CONTAINS, fragment

    rule, created = CategoryRule.objects.get_or_create(
        household=transaction.household,
        match_type=match_type,
        pattern=pattern,
        defaults={"category": category, "origin": CategoryRule.Origin.LEARNED},
    )
    if not created and rule.category_id != category.pk:
        # The user changed their mind about this merchant; follow them.
        rule.category = category
        rule.is_active = True
        rule.save(update_fields=["category", "is_active", "updated_at"])

    return rule


# Words that appear in most narrations and identify nothing on their own.
NOISE_TOKENS = frozenset(
    {
        "ACH",
        "ATM",
        "ATW",
        "CREDIT",
        "CR",
        "DEBIT",
        "DR",
        "FROM",
        "IMPS",
        "INR",
        "LIMITED",
        "LTD",
        "NEFT",
        "PAYMENT",
        "POS",
        "PVT",
        "REF",
        "RTGS",
        "TO",
        "TRANSFER",
        "TXN",
        "UPI",
    }
)

MIN_FRAGMENT_LENGTH = 4

_NON_ALPHA = re.compile(r"[^A-Za-z]+")


def distinctive_fragment(description: str) -> str | None:
    """The most identifying word in a narration.

    Picks the longest alphabetic token that is neither a banking keyword nor
    part of a reference number, so `UPI-SWIGGY-...-PAYMENT` yields `SWIGGY`.
    """
    tokens = [
        token
        for token in _NON_ALPHA.split(normalise_for_matching(description))
        if len(token) >= MIN_FRAGMENT_LENGTH and token not in NOISE_TOKENS
    ]
    return max(tokens, key=len) if tokens else None
