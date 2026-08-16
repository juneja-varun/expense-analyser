"""HDFC Bank savings and current account statements.

The "Download as XLS" option in HDFC net banking actually produces a
**delimited text file** with an `.xls` extension, not a real spreadsheet. It
looks like this:

    HDFC BANK LTD
    Account Branch : KORAMANGALA
    ...roughly twenty lines of account summary...

    Date       Narration    Chq./Ref.No.  Value Dt   Withdrawal Amt.  Deposit Amt.  Closing Balance
    03/04/24   UPI-SWIGGY   0000000000    03/04/24   450.00           0.00          52,340.15

Columns are located by header name rather than position, because HDFC varies
the header length between account types and has added columns over time. A
fixed "skip 20 lines, take column 4" parser breaks the first time that happens.
"""

from __future__ import annotations

from decimal import Decimal

from apps.parsers.base import (
    BaseParser,
    Confidence,
    ParsedFile,
    ParsedStatement,
    ParsedTransaction,
    ParseError,
)
from apps.parsers.utils.amounts import parse_amount, parse_signed_amount
from apps.parsers.utils.dates import parse_date, parse_date_or_none
from apps.parsers.utils.tables import (
    detect_delimiter,
    drop_blank_rows,
    read_delimited,
    rows_after_header,
)

# Header fragments, lowercase. Matching is substring-based, so "withdrawal"
# matches "Withdrawal Amt.".
COLUMNS = {
    "date": ("date",),
    "narration": ("narration", "description", "particulars"),
    "reference": ("chq", "ref"),
    "value_date": ("value dt", "value date"),
    "withdrawal": ("withdrawal",),
    "deposit": ("deposit",),
    "balance": ("closing balance", "balance"),
}

REQUIRED_HEADERS = ("date", "narration", "withdrawal", "deposit")


class HDFCBankStatementParser(BaseParser):
    bank_slug = "hdfc"
    display_name = "HDFC Bank — Savings/Current"
    statement_kind = "bank"
    file_formats = ["xls", "xlsx", "csv", "txt"]

    @classmethod
    def can_parse(cls, file: ParsedFile) -> Confidence:
        text = file.head.lower()

        has_hdfc = "hdfc" in text
        # HDFC's narration column is the giveaway when the bank name has been
        # trimmed off — few other Indian banks use that word as a header.
        has_layout = "narration" in text and "withdrawal" in text

        if has_hdfc and has_layout:
            return Confidence.STRONG
        if has_hdfc:
            return Confidence.LIKELY
        if has_layout and "closing balance" in text:
            return Confidence.WEAK
        return Confidence.NONE

    def parse(self, file: ParsedFile) -> ParsedStatement:
        text = file.text
        if not text.strip():
            raise ParseError(
                "This file appears to be empty. If you downloaded it from HDFC net "
                "banking, try the 'Delimited' export rather than the PDF."
            )

        rows = read_delimited(text, detect_delimiter(text))

        try:
            header, body = rows_after_header(rows, REQUIRED_HEADERS)
        except ValueError as exc:
            raise ParseError(
                "Could not find the transaction table. Expected a header row with "
                f"{', '.join(REQUIRED_HEADERS)}. This may be a statement layout we "
                "haven't seen — please open an issue with the layout described."
            ) from exc

        index = self._map_columns(header)
        transactions: list[ParsedTransaction] = []
        closing_balance: Decimal | None = None

        for row in drop_blank_rows(body):
            transaction = self._parse_row(row, index, header)
            if transaction is None:
                continue
            transactions.append(transaction)
            if transaction.balance is not None:
                closing_balance = transaction.balance

        if not transactions:
            raise ParseError(
                "Found the transaction table but no readable rows in it. "
                "If the statement covers a period with no activity this is expected."
            )

        dates = sorted(t.txn_date for t in transactions)
        opening = transactions[0].balance
        if opening is not None:
            opening = opening - transactions[0].amount

        return self.build_statement(
            transactions,
            source_hint=self._find_account_number(file.head),
            period_start=dates[0],
            period_end=dates[-1],
            opening_balance=opening,
            closing_balance=closing_balance,
        )

    # -- internals -------------------------------------------------------

    def _map_columns(self, header: list[str]) -> dict[str, int]:
        """Map logical column names to their position in this file's header."""
        lowered = [cell.lower() for cell in header]
        index: dict[str, int] = {}

        for name, fragments in COLUMNS.items():
            for position, cell in enumerate(lowered):
                if position in index.values():
                    continue
                if any(fragment in cell for fragment in fragments):
                    index[name] = position
                    break

        missing = [c for c in REQUIRED_HEADERS if c not in index]
        if missing:
            raise ParseError(
                f"Statement header is missing expected column(s): {', '.join(missing)}. "
                f"Found: {', '.join(header)}"
            )
        return index

    def _parse_row(
        self, row: list[str], index: dict[str, int], header: list[str]
    ) -> ParsedTransaction | None:
        def cell(name: str) -> str:
            position = index.get(name)
            if position is None or position >= len(row):
                return ""
            return row[position]

        raw_date = cell("date")
        if not raw_date:
            return None

        try:
            txn_date = parse_date(raw_date)
        except ValueError:
            # Footer lines ("*** End of statement ***", disclaimers) land here.
            # Skipping them is correct; a row that fails on a *date-looking*
            # value is a real problem and surfaces below.
            return None

        try:
            amount = parse_signed_amount(debit=cell("withdrawal"), credit=cell("deposit"))
        except ValueError as exc:
            raise ParseError(
                f"Could not read the amount on {raw_date}: {exc}. "
                f"Row: {dict(zip(header, row, strict=False))}"
            ) from exc

        if amount == 0:
            # HDFC prints 0.00 in both columns on some informational rows.
            return None

        balance_text = cell("balance")
        balance = parse_amount(balance_text) if balance_text else None

        return ParsedTransaction(
            txn_date=txn_date,
            value_date=parse_date_or_none(cell("value_date")),
            description=cell("narration"),
            amount=amount,
            balance=balance,
            reference=cell("reference") or None,
            raw=dict(zip(header, row, strict=False)),
        )

    def _find_account_number(self, head: str) -> str | None:
        """Pull a masked account number out of the header block, if present."""
        import re

        match = re.search(r"(?i)account\s*(?:no\.?|number)?\s*[:\-]?\s*([X*\d]{6,20})", head)
        if not match:
            return None
        number = match.group(1)
        # Never keep a full account number — the last four are all we need to
        # match an upload to an account.
        return f"XXXXXXXX{number[-4:]}" if len(number) > 4 else number
