"""ICICI Bank credit card statements (PDF).

Card statements are a different shape from bank statements in two ways that
matter, and this parser exists partly to prove the interface handles both:

1. **No ruling lines.** The PDF has no table borders, so `extract_tables` finds
   nothing useful. Parsing is line-oriented against the text layer instead.
2. **Signs are inverted.** A card statement is written from the issuer's point
   of view: a purchase is printed as a positive number and a payment or refund
   carries a `CR` suffix. We normalise to the same convention as every other
   statement — **negative is money leaving you** — so nothing downstream has to
   know which kind of statement a transaction came from.

The emailed version is usually password-protected; `utils.pdf` handles that.
"""

from __future__ import annotations

import re
from decimal import Decimal

from apps.parsers.base import (
    BaseParser,
    Confidence,
    ParsedFile,
    ParsedStatement,
    ParsedTransaction,
    ParseError,
)
from apps.parsers.utils.amounts import parse_amount
from apps.parsers.utils.dates import parse_date, parse_date_or_none

# A transaction line: date, description, amount, optional CR marker.
TRANSACTION_LINE = re.compile(
    r"^\s*(?P<date>\d{2}[/-]\d{2}[/-]\d{2,4})\s+"
    r"(?P<description>.+?)\s+"
    r"(?P<amount>[\d,]+\.\d{2})"
    r"(?P<credit>\s*CR)?\s*$",
    re.IGNORECASE,
)

CARD_NUMBER = re.compile(r"(?i)card\s*(?:number|no\.?)\s*[:\-]?\s*([X*\d\s]{12,25})")
PERIOD = re.compile(
    r"(?i)statement\s*period\s*[:\-]?\s*"
    # \u2013 is an en dash: statements print "05/03/2024 - 04/04/2024" both ways.
    r"(\d{2}[/-]\d{2}[/-]\d{2,4})\s*(?:to|-|\u2013)\s*(\d{2}[/-]\d{2}[/-]\d{2,4})"
)
TOTAL_DUE = re.compile(r"(?i)total\s*amount\s*due\s*[:\-]?\s*([\d,]+\.\d{2})")

# Lines that match the transaction shape but are summary rows, not transactions.
SUMMARY_PREFIXES = (
    "total amount due",
    "minimum amount due",
    "credit limit",
    "available credit",
    "previous balance",
    "opening balance",
    "closing balance",
)


class ICICICreditCardParser(BaseParser):
    bank_slug = "icici"
    display_name = "ICICI Bank — Credit Card"
    statement_kind = "credit_card"
    file_formats = ["pdf"]

    # Phrases that mark a savings/current account statement. ICICI issues both,
    # and the two layouts are nothing alike — a bank statement handed to this
    # parser read the closing balance as the transaction amount and turned a
    # salary credit into a large debit, without failing.
    BANK_STATEMENT_MARKERS = (
        "savings account",
        "current account",
        "statement of transactions",
        "withdrawals",
        "deposits",
    )

    @classmethod
    def can_parse(cls, file: ParsedFile) -> Confidence:
        text = file.head.lower()
        if "icici" not in text:
            return Confidence.NONE

        # Rule this parser out explicitly rather than scoring low: a wrong
        # parser that succeeds is far worse than one that declines.
        if any(marker in text for marker in cls.BANK_STATEMENT_MARKERS):
            return Confidence.NONE

        if "credit card statement" in text:
            return Confidence.STRONG
        if "card number" in text or "payment due date" in text:
            return Confidence.LIKELY
        # An ICICI document of some kind, but not evidently a card statement.
        # Below the auto-dispatch bar, so the user is asked rather than guessed at.
        return Confidence.WEAK

    def parse(self, file: ParsedFile) -> ParsedStatement:
        text = file.text
        if not text.strip():
            raise ParseError(
                "No text could be read from this PDF. If it is a scan or photo "
                "rather than the file your bank emailed, download the original — "
                "scanned statements are not supported."
            )

        transactions = self._parse_transactions(text)
        if not transactions:
            raise ParseError(
                "No transactions found. This looks like an ICICI credit card "
                "statement, but none of its lines matched the expected "
                "'date  description  amount' layout."
            )

        period_start, period_end = self._parse_period(text)
        dates = sorted(t.txn_date for t in transactions)

        return self.build_statement(
            transactions,
            source_hint=self._parse_card_number(text),
            period_start=period_start or dates[0],
            period_end=period_end or dates[-1],
            closing_balance=self._parse_total_due(text),
        )

    # -- internals -------------------------------------------------------

    def _parse_transactions(self, text: str) -> list[ParsedTransaction]:
        transactions: list[ParsedTransaction] = []

        for line in text.splitlines():
            match = TRANSACTION_LINE.match(line)
            if not match:
                continue

            description = match.group("description").strip()
            if description.lower().startswith(SUMMARY_PREFIXES):
                continue

            try:
                txn_date = parse_date(match.group("date"))
            except ValueError:
                continue

            amount = parse_amount(match.group("amount"))

            # Zero-value rows (waived charges, informational lines) carry no
            # financial meaning and would only clutter the transaction list.
            if amount == 0:
                continue

            is_credit = bool(match.group("credit"))
            # The sign flip: a card purchase reduces what you have, so it is
            # negative here even though the statement prints it positive.
            signed = amount if is_credit else -amount

            transactions.append(
                ParsedTransaction(
                    txn_date=txn_date,
                    description=description,
                    amount=signed,
                    raw={"line": line.strip()},
                )
            )

        return transactions

    def _parse_card_number(self, text: str) -> str | None:
        match = CARD_NUMBER.search(text)
        if not match:
            return None
        digits = re.sub(r"\s+", "", match.group(1))
        # Statements already mask these, but never store more than the last
        # four regardless of what the file contains.
        return f"XXXXXXXXXXXX{digits[-4:]}" if len(digits) > 4 else digits

    def _parse_period(self, text: str) -> tuple[object | None, object | None]:
        match = PERIOD.search(text)
        if not match:
            return None, None
        return parse_date_or_none(match.group(1)), parse_date_or_none(match.group(2))

    def _parse_total_due(self, text: str) -> Decimal | None:
        match = TOTAL_DUE.search(text)
        if not match:
            return None
        # Outstanding on a card is money owed, so it is negative as a balance.
        return -parse_amount(match.group(1))
