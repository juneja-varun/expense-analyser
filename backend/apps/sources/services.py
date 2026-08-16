"""Matching an uploaded statement to the account it belongs to."""

from __future__ import annotations

from apps.accounts.models import Household
from apps.parsers.base import ParsedStatement
from apps.sources.models import Source

__all__ = ["resolve_source"]


def resolve_source(household: Household, statement: ParsedStatement) -> Source:
    """Find or create the account an uploaded statement belongs to.

    Matching is on `(bank_slug, account_hint)`. When the statement prints no
    account number there is nothing reliable to match on, so we fall back to
    the first non-archived source for that bank and statement kind rather than
    creating a duplicate on every upload.
    """
    kind = (
        Source.Kind.CREDIT_CARD if statement.statement_kind == "credit_card" else Source.Kind.BANK
    )

    if statement.source_hint:
        source, _ = Source.objects.get_or_create(
            household=household,
            bank_slug=statement.bank_slug,
            account_hint=statement.source_hint,
            defaults={
                "name": _default_name(statement, kind),
                "kind": kind,
            },
        )
        return source

    existing = (
        Source.objects.for_household(household)
        .filter(bank_slug=statement.bank_slug, kind=kind, is_archived=False)
        .first()
    )
    if existing is not None:
        return existing

    return Source.objects.create(
        household=household,
        bank_slug=statement.bank_slug,
        kind=kind,
        name=_default_name(statement, kind),
    )


def _default_name(statement: ParsedStatement, kind: str) -> str:
    """A readable name the user can rename later."""
    bank = (statement.bank_slug or "Account").upper()
    suffix = "Credit Card" if kind == Source.Kind.CREDIT_CARD else "Account"
    return f"{bank} {suffix}"
