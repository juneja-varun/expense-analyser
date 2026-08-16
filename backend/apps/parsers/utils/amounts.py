"""Parsing Indian statement amounts.

Between them, Indian banks manage to write the same number as `1,20,450.00`,
`1,20,450.00 Dr`, `(1,20,450.00)`, `1,20,450.00-`, `Rs. 1,20,450.00` and
`₹1,20,450`. This module turns all of those into a signed `Decimal`.

Never use `float` for money.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

__all__ = ["is_amount", "parse_amount", "parse_signed_amount"]

# Currency markers and whitespace to strip before parsing. `\s` covers the
# non-breaking spaces that PDF exports often use as thousands separators.
_NOISE = re.compile(r"(?i)(?:₹|rs\.?|inr|\s)")

# Trailing Dr/Cr markers. Dr is money out, Cr is money in — the opposite of
# what a naive reading suggests, because the statement is written from the
# bank's point of view.
_DEBIT_MARKER = re.compile(r"(?i)\b(?:dr|debit)\.?$")
_CREDIT_MARKER = re.compile(r"(?i)\b(?:cr|credit)\.?$")

_NUMERIC = re.compile(r"^-?\d+(?:\.\d+)?$")


def _strip_to_number(value: str) -> tuple[str, bool]:
    """Reduce a printed amount to bare digits. Returns (digits, is_negative)."""
    text = str(value).strip()
    if not text:
        raise ValueError("empty amount")

    negative = False

    # Accounting style: (1,234.00) means negative.
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()

    # Dr/Cr markers are matched *before* whitespace is stripped: the word
    # boundary they rely on disappears once "1,234.00 Cr" becomes "1,234.00Cr".
    if _DEBIT_MARKER.search(text):
        negative = True
        text = _DEBIT_MARKER.sub("", text)
    elif _CREDIT_MARKER.search(text):
        text = _CREDIT_MARKER.sub("", text)

    text = _NOISE.sub("", text)

    # Trailing minus: some exports write 1234.00-
    if text.endswith("-"):
        negative = True
        text = text[:-1]
    elif text.startswith("-"):
        negative = True
        text = text[1:]
    elif text.startswith("+"):
        text = text[1:]

    # Grouping separators. Indian grouping (1,20,450.00) is irregular, so the
    # only safe rule is to drop commas entirely rather than infer a locale.
    text = text.replace(",", "")

    if not text or not _NUMERIC.match(text):
        raise ValueError(f"could not read {value!r} as an amount")

    return text, negative


def parse_amount(value: str | int | float | Decimal) -> Decimal:
    """Parse an amount, honouring any sign printed in the string.

    >>> parse_amount("1,20,450.00")
    Decimal('120450.00')
    >>> parse_amount("(1,234.00)")
    Decimal('-1234.00')
    >>> parse_amount("500.00 Dr")
    Decimal('-500.00')
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        # Only reachable via a spreadsheet cell, where the float came from the
        # file rather than from our own arithmetic. str() keeps the printed
        # value rather than the binary approximation.
        return Decimal(str(value))

    digits, negative = _strip_to_number(value)
    try:
        amount = Decimal(digits)
    except InvalidOperation as exc:
        raise ValueError(f"could not read {value!r} as an amount") from exc
    return -amount if negative else amount


def parse_signed_amount(
    debit: str | None = None,
    credit: str | None = None,
) -> Decimal:
    """Combine separate debit and credit columns into one signed amount.

    The common layout for Indian bank statements: two columns, one of which is
    blank on any given row. Debits come back negative.

    >>> parse_signed_amount(debit="1,500.00", credit="")
    Decimal('-1500.00')
    >>> parse_signed_amount(debit="", credit="2,000.00")
    Decimal('2000.00')
    """
    debit_value = _optional(debit)
    credit_value = _optional(credit)

    if debit_value is None and credit_value is None:
        raise ValueError("row has neither a debit nor a credit amount")
    # Some banks print 0.00 in the unused column rather than leaving it blank,
    # so a zero on one side is not a conflict — only two non-zero values are.
    if debit_value and credit_value:
        raise ValueError(f"row has both a debit ({debit}) and a credit ({credit}) amount")

    if debit_value:
        return -abs(debit_value)
    if credit_value:
        return abs(credit_value)
    return Decimal("0.00")


def _optional(value: str | None) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "--", "NA", "N/A", "."}:
        return None
    try:
        return parse_amount(text)
    except ValueError:
        return None


def is_amount(value: str) -> bool:
    """True if the string reads as an amount. Useful for locating columns."""
    try:
        parse_amount(value)
    except (ValueError, TypeError):
        return False
    return True
