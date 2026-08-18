"""ICICI Bank savings and current account statements (PDF).

Written from a real statement, and the layout is the messiest yet supported.
Two things drive the design:

**1. The deposit/withdrawal column cannot be read.** The header promises
`DATE MODE PARTICULARS DEPOSITS WITHDRAWALS BALANCE`, but PDF text extraction
collapses the empty column, so a row arrives with exactly one amount before the
balance:

    01-07-2026 691.00 3,34,987.35

Nothing in that line says whether 691.00 went in or out. The **running balance
does**: the sign is `balance - previous_balance`, and the printed amount is used
to check that reading rather than to produce it. A row whose delta disagrees
with its printed amount is reported instead of guessed at.

**2. Descriptions wrap across lines, above and below their own row.** The
particulars column is much wider than the extractor's line, so a single
transaction looks like:

    Amazon Pay Groceries                            <- merchant, above the row
    UPI/Amazon Pay/amazonpaygroce/You are pa/AXIS   <- still above
    01-07-2026 691.00 3,34,987.35                   <- the row itself
    BANK/5124.../APL019f1d57.../                    <- reference tail, below

The merchant name — the part a person recognises and the categorisation rules
match on — is in the lines *preceding* the row. Reference tails below it are
absorbed into the same transaction so they don't contaminate the next one.
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

AMOUNT = r"[\d,]+\.\d{2}"

# A transaction row: date, optional inline particulars, amount, running balance.
# DEPOSITS and WITHDRAWALS are separate columns on paper. Text extraction emits
# nothing for an empty cell, so most rows arrive with a single amount — but a
# statement that fills the unused column with 0.00 produces two. Capture either
# shape; which of them is the real figure is decided by the balance, below.
TRANSACTION_ROW = re.compile(
    rf"^\s*(?P<date>\d{{2}}-\d{{2}}-\d{{4}})\s+"
    rf"(?P<particulars>.*?)\s*"
    rf"(?P<amounts>{AMOUNT}(?:\s+{AMOUNT})?)\s+(?P<balance>{AMOUNT})\s*$"
)

# The brought-forward row carries the opening balance and no amount.
OPENING_ROW = re.compile(
    rf"^\s*(?P<date>\d{{2}}-\d{{2}}-\d{{4}})\s+B/F\s+(?P<balance>{AMOUNT})\s*$"
)

TABLE_HEADER = re.compile(r"(?i)\bDATE\b.*\bPARTICULARS\b.*\bBALANCE\b")

PERIOD = re.compile(
    r"(?i)for the period\s+(?P<start>\w+\s+\d{1,2},\s*\d{4})\s*-\s*(?P<end>\w+\s+\d{1,2},\s*\d{4})"
)
ACCOUNT = re.compile(r"(?i)Savings Account\s+([X*]+\d{3,6})|Savings A/c\s+([X*]+\d{3,6})")

PERIOD_FORMATS = ("%B %d, %Y", "%b %d, %Y")

# Lines that are page furniture rather than statement content.
NOISE = re.compile(
    r"(?i)^\s*(page \d+ of \d+|"
    r"statement of transactions|"
    r"date\s+mode\s+particulars|"
    r"this is a (computer|system) generated|"
    r"total\b|"
    r"legends?:|"
    r"m-\d+)"
)

# A reference tail belonging to the row above: bank/UPI plumbing, no letters a
# person would recognise as a payee.
#
# Two shapes, because the space is what separates them from a merchant name:
#
#   BANK/656022356612/APL019f5a38957d658276d0afc0bd956488/   no spaces at all
#   MMT/IMPS/619521828164/SIMMI SHAR/CNRB0001387            spaces, but carries
#                                                            a reference number
#
# The second shape needs the digit run to earn its spaces. Without that guard
# the pattern also swallows the *next* transaction's merchant — "Euronet
# Services India Pvt Ltd" is a payee, not plumbing — and that row would then
# be left with no description at all.
REFERENCE_TAIL = re.compile(
    r"^(?:[A-Z0-9]*(?:BANK|/)[A-Z0-9/@.\-]*" r"|(?=.*\d{6})[A-Z0-9 ]*/[A-Z0-9/@.\- ]*)$",
    re.IGNORECASE,
)


class ICICIBankStatementParser(BaseParser):
    bank_slug = "icici_bank"
    display_name = "ICICI Bank — Savings/Current"
    statement_kind = "bank"
    file_formats = ["pdf"]

    @classmethod
    def can_parse(cls, file: ParsedFile) -> Confidence:
        text = file.head.lower()
        if "icici" not in text:
            return Confidence.NONE
        if "statement of transactions" in text and (
            "savings account" in text or "current account" in text
        ):
            return Confidence.STRONG
        if "savings a/c" in text or "account details" in text:
            return Confidence.LIKELY
        return Confidence.NONE

    def parse(self, file: ParsedFile) -> ParsedStatement:
        text = file.text
        if not text.strip():
            raise ParseError(
                "No text could be read from this PDF. If it is a scan rather than the "
                "file ICICI sent, download the original from net banking."
            )

        lines = text.splitlines()
        start = self._table_start(lines)
        transactions, opening, closing = self._parse_rows(lines[start:])

        if not transactions:
            raise ParseError(
                "Found the statement table but no readable transaction rows. If this "
                "statement covers a period with no activity that is expected; otherwise "
                "please report it, as the layout may have changed."
            )

        period_start, period_end = self._parse_period(text)
        dates = sorted(t.txn_date for t in transactions)

        return self.build_statement(
            transactions,
            source_hint=self._parse_account(text),
            period_start=period_start or dates[0],
            period_end=period_end or dates[-1],
            opening_balance=opening,
            closing_balance=closing,
        )

    # -- internals -------------------------------------------------------

    def _table_start(self, lines: list[str]) -> int:
        """Index just past the transaction table's header row.

        ICICI puts about forty lines of account summary first, and those contain
        amounts that would otherwise be read as transactions.
        """
        for index, line in enumerate(lines):
            if TABLE_HEADER.search(line):
                return index + 1
        # Some statements repeat the header only on later pages; fall back to
        # the brought-forward row, which always precedes the first transaction.
        for index, line in enumerate(lines):
            if OPENING_ROW.match(line):
                return index
        raise ParseError(
            "Could not find the transaction table. Expected a header row containing "
            "DATE, PARTICULARS and BALANCE."
        )

    def _parse_rows(
        self, lines: list[str]
    ) -> tuple[list[ParsedTransaction], Decimal | None, Decimal | None]:
        transactions: list[ParsedTransaction] = []
        pending: list[str] = []
        previous_balance: Decimal | None = None
        opening: Decimal | None = None

        for raw in lines:
            line = raw.strip()
            if not line or NOISE.match(line):
                continue

            opening_match = OPENING_ROW.match(line)
            if opening_match:
                previous_balance = parse_amount(opening_match.group("balance"))
                opening = previous_balance
                pending.clear()
                continue

            row = TRANSACTION_ROW.match(line)
            if not row:
                if transactions and REFERENCE_TAIL.match(line) and not pending:
                    # Plumbing belonging to the row above; keep it with that
                    # transaction rather than letting it head the next one.
                    transactions[-1] = self._append_description(transactions[-1], line)
                else:
                    pending.append(line)
                continue

            transaction, previous_balance = self._build_transaction(row, pending, previous_balance)
            transactions.append(transaction)
            pending = []

        return transactions, opening, previous_balance

    def _build_transaction(
        self, row: re.Match[str], pending: list[str], previous_balance: Decimal | None
    ) -> tuple[ParsedTransaction, Decimal]:
        balance = parse_amount(row.group("balance"))
        printed = [parse_amount(value) for value in row.group("amounts").split()]

        if previous_balance is None:
            raise ParseError(
                "The statement's opening balance is missing, so deposits cannot be told "
                "apart from withdrawals. Please report this statement layout."
            )

        # The direction the columns do not survive extraction to tell us.
        amount = balance - previous_balance

        # Accept the row if any printed figure agrees with the movement: a
        # single amount when the unused column is blank, or one of two when it
        # is filled with 0.00. A row where none agrees means a row was missed
        # or misread — the balance chain then no longer reconciles, and every
        # later row would be wrong too, so it is refused rather than guessed at.
        if not any(abs(amount) == value for value in printed):
            shown = " and ".join(str(value) for value in printed)
            raise ParseError(
                f"On {row.group('date')} the running balance moves by {abs(amount)} but "
                f"the statement prints {shown}. Rather than guess which is right, this "
                "row is being refused — please report it."
            )

        description_parts = [*pending, row.group("particulars").strip()]
        description = " ".join(part for part in description_parts if part)

        return (
            ParsedTransaction(
                txn_date=parse_date(row.group("date")),
                description=description or "(no description)",
                amount=amount,
                balance=balance,
                raw={"line": row.group(0).strip()},
            ),
            balance,
        )

    def _append_description(self, transaction: ParsedTransaction, extra: str) -> ParsedTransaction:
        from dataclasses import replace

        return replace(transaction, description=f"{transaction.description} {extra}".strip())

    def _parse_period(self, text: str):
        match = PERIOD.search(text)
        if not match:
            return None, None
        return (
            parse_date_or_none(match.group("start"), PERIOD_FORMATS),
            parse_date_or_none(match.group("end"), PERIOD_FORMATS),
        )

    def _parse_account(self, text: str) -> str | None:
        match = ACCOUNT.search(text)
        if not match:
            return None
        number = match.group(1) or match.group(2)
        return f"XXXXXXXX{number[-4:]}" if len(number) > 4 else number
