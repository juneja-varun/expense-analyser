from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import HouseholdScopedModel

MAX_PATTERN_LENGTH = 500

# UPI narrations are the dominant transaction shape in India and follow a loose
# convention: UPI-<PAYEE>-<vpa@handle>-<note>. The VPA is the most stable
# identifier in the string — the payee name and note vary between banks for the
# same merchant, but the VPA does not.
#
# The narration is split on delimiters first rather than matched with one
# regex. A hyphen is both legal inside a VPA and the delimiter banks use most,
# so a single pattern greedily swallows the preceding fields:
# "UPI-SWIGGY-swiggy@examplebank" yields "upi-swiggy-swiggy@examplebank".
# Splitting first is less clever and gets the common case right.
#
# Trade-off: a VPA that genuinely contains a hyphen ("shop-name@paytm") is
# truncated to the part after it. That is consistent for a given merchant, so
# rules still match reliably; it is only slightly less specific.
_DELIMITERS = re.compile(r"[\s/,|:;()\[\]-]+")
_VPA_TOKEN = re.compile(r"^[a-z0-9][a-z0-9._]{1,60}@[a-z][a-z0-9.]{1,30}$", re.IGNORECASE)

_WHITESPACE = re.compile(r"\s+")

# ICICI (and several other banks) end a UPI narration with the routing details:
#
#   <PAYEE> UPI/<payee>/<vpa>/<note>/<REMITTER BANK>/<reference>/<txn id>/
#
# The bank in that tail is how the money travelled, not who was paid — and it
# is a bank or wallet name, which is exactly what merchant patterns look for.
# Left in place, `CONTAINS "AIRTEL"` files every transfer routed through Airtel
# Payments Bank as an internet bill, and an `AMAZON` pattern would catch
# anything funded from Amazon Pay's RBL account. Both are silent: the amount is
# right, so nothing looks wrong until a budget is inexplicably over.
#
# The bank name is truncated by the statement itself (`YES BANK L`,
# `Kotak Mahi`), so it is matched by position rather than by name.
_RAIL_TAIL = re.compile(r"/[A-Za-z][A-Za-z .&-]{2,24}/\d{9,}/[A-Za-z0-9 ]+/?\s*$")


def normalise_for_matching(description: str) -> str:
    """Upper-case, whitespace-collapsed form used for matching only.

    The stored description is never modified — users need to recognise their
    own transactions.
    """
    return _WHITESPACE.sub(" ", description).strip().upper()


def matchable_text(description: str) -> str:
    """The part of a narration that says what was paid for.

    Rules match against this rather than the raw description, so a rule
    describes what you bought and not which bank moved the money. The stored
    description is untouched — users need to recognise their own transactions,
    reference numbers and all.
    """
    return _RAIL_TAIL.sub("", description).rstrip("/ ")


def extract_vpa(description: str) -> str | None:
    """The UPI VPA in a narration, lower-cased, or None."""
    for token in _DELIMITERS.split(description):
        if _VPA_TOKEN.match(token):
            return token.lower()
    return None


class CategoryRule(HouseholdScopedModel):
    """A rule mapping transaction descriptions to a category.

    Deterministic and offline by design: this is the whole categorisation
    engine, not a fallback for one. An optional LLM may later label what the
    rules miss, but the app has to be useful with no network and no API key.

    Rules also make the app improve through use — recategorising a transaction
    creates a `LEARNED` rule, so the same merchant is never re-classified by
    hand twice.
    """

    class MatchType(models.TextChoices):
        CONTAINS = "contains", _("Description contains")
        EXACT = "exact", _("Description is exactly")
        STARTS_WITH = "starts_with", _("Description starts with")
        REGEX = "regex", _("Description matches regex")
        UPI_VPA = "upi_vpa", _("UPI VPA is")

    class Origin(models.TextChoices):
        USER = "user", _("Created by the user")
        LEARNED = "learned", _("Learned from a recategorisation")
        BUILTIN = "builtin", _("Shipped with the app")

    # Defaults chosen so the precedence order falls out of a single ORDER BY:
    # an explicit rule always beats one we learned, which beats one we shipped.
    DEFAULT_PRIORITY = {Origin.USER: 100, Origin.LEARNED: 50, Origin.BUILTIN: 10}

    category = models.ForeignKey(
        "categories.Category",
        on_delete=models.CASCADE,
        related_name="rules",
    )
    match_type = models.CharField(
        max_length=16, choices=MatchType.choices, default=MatchType.CONTAINS
    )
    pattern = models.CharField(max_length=MAX_PATTERN_LENGTH)
    origin = models.CharField(max_length=16, choices=Origin.choices, default=Origin.USER)
    priority = models.IntegerField(
        default=0,
        help_text="Higher wins. Defaults by origin; set explicitly to override.",
    )
    is_active = models.BooleanField(default=True)
    match_count = models.PositiveIntegerField(
        default=0,
        help_text="How many transactions this rule has categorised. Surfaces dead rules.",
    )

    class Meta:
        ordering = ["-priority", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["household", "match_type", "pattern"],
                name="unique_rule_per_household",
            ),
        ]
        indexes = [models.Index(fields=["household", "is_active", "-priority"])]

    def __str__(self) -> str:
        return f"{self.get_match_type_display()} {self.pattern!r} → {self.category}"

    def clean(self) -> None:
        if not self.pattern.strip():
            raise ValidationError({"pattern": "A rule needs a pattern to match on."})

        if self.category_id and self.category.household_id != self.household_id:
            raise ValidationError({"category": "Category belongs to a different household."})

        if self.match_type == self.MatchType.REGEX:
            try:
                re.compile(self.pattern)
            except re.error as exc:
                raise ValidationError(
                    {"pattern": f"Not a valid regular expression: {exc}"}
                ) from exc

    def save(self, *args, **kwargs) -> None:
        self.pattern = self.pattern.strip()
        if self.match_type == self.MatchType.UPI_VPA:
            self.pattern = self.pattern.lower()
        if not self.priority:
            self.priority = self.DEFAULT_PRIORITY.get(self.Origin(self.origin), 0)
        self.clean()
        super().save(*args, **kwargs)

    def matches(self, description: str) -> bool:
        """Does this rule apply to the given description?"""
        if not self.is_active:
            return False

        if self.match_type == self.MatchType.UPI_VPA:
            return extract_vpa(description) == self.pattern

        haystack = normalise_for_matching(matchable_text(description))
        needle = normalise_for_matching(self.pattern)

        if self.match_type == self.MatchType.CONTAINS:
            return needle in haystack
        if self.match_type == self.MatchType.EXACT:
            return haystack == needle
        if self.match_type == self.MatchType.STARTS_WITH:
            return haystack.startswith(needle)
        if self.match_type == self.MatchType.REGEX:
            try:
                return (
                    re.search(self.pattern, matchable_text(description), re.IGNORECASE) is not None
                )
            except re.error:
                # A rule saved before a Python regex change, or edited in the
                # database directly. One broken rule must not stop the rest
                # from categorising.
                return False
        return False
