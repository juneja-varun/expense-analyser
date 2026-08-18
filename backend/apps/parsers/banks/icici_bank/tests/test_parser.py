"""ICICI savings statement parsing.

The golden-file harness already checks the whole fixture round-trips. These
cover the two things that make this layout hard, and that a future change could
break without the golden file noticing why.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from apps.parsers.banks.icici.parser import ICICICreditCardParser
from apps.parsers.banks.icici_bank.parser import ICICIBankStatementParser
from apps.parsers.base import Confidence, ParsedFile, ParseError

FIXTURES = Path(__file__).resolve().parents[3] / "banks"
SAVINGS = FIXTURES / "icici_bank" / "tests" / "fixtures" / "icici_savings_2026_07.pdf"
CREDIT_CARD = FIXTURES / "icici" / "tests" / "fixtures" / "icici_credit_card_2024_04.pdf"


class FakeFile:
    """Lets these cases state a layout inline instead of generating a PDF."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.head = text[:4096]
        self.extension = "pdf"
        self.filename = "statement.pdf"


HEADER = (
    "ICICI Bank Limited\n"
    "Statement of Transactions in Savings Account XXXXXXXX0136 in INR for the period "
    "July 01, 2026 - July 31, 2026\n"
    "DATE MODE PARTICULARS DEPOSITS WITHDRAWALS BALANCE\n"
)


def parse(body: str):
    return ICICIBankStatementParser().parse(FakeFile(HEADER + body))


class TestSignComesFromTheRunningBalance:
    """The columns don't survive extraction.

    `DEPOSITS` and `WITHDRAWALS` are separate columns on paper, but the empty
    one collapses, so a row arrives with a single amount and nothing saying
    which direction it went. The balance is the only witness.
    """

    def test_a_falling_balance_is_a_debit(self) -> None:
        statement = parse("01-07-2026 B/F 1,000.00\nSHOP\n02-07-2026 250.00 750.00\n")

        assert statement.transactions[0].amount == Decimal("-250.00")

    def test_a_rising_balance_is_a_credit(self) -> None:
        """The same row shape as a debit — only the balance distinguishes them."""
        statement = parse("01-07-2026 B/F 1,000.00\nSALARY\n02-07-2026 250.00 1,250.00\n")

        assert statement.transactions[0].amount == Decimal("250.00")

    def test_the_printed_amount_is_used_to_check_not_to_decide(self) -> None:
        """A row whose delta disagrees with its printed amount is refused.

        Guessing here would silently corrupt every downstream number, which is
        exactly the failure this parser exists to avoid.
        """
        with pytest.raises(ParseError, match="(?i)rather than guess"):
            parse("01-07-2026 B/F 1,000.00\nSHOP\n02-07-2026 250.00 900.00\n")

    def test_a_missing_opening_balance_is_refused(self) -> None:
        with pytest.raises(ParseError, match="opening balance is missing"):
            parse("SHOP\n02-07-2026 250.00 750.00\n")

    def test_balances_chain_across_rows(self) -> None:
        statement = parse(
            "01-07-2026 B/F 1,000.00\n"
            "A\n02-07-2026 100.00 900.00\n"
            "B\n03-07-2026 400.00 1,300.00\n"
            "C\n04-07-2026 300.00 1,000.00\n"
        )

        assert [t.amount for t in statement.transactions] == [
            Decimal("-100.00"),
            Decimal("400.00"),
            Decimal("-300.00"),
        ]
        assert statement.closing_balance == Decimal("1000.00")


class TestWrappedDescriptions:
    def test_the_merchant_name_above_the_row_is_captured(self) -> None:
        """The recognisable part of the description sits on lines *before* the
        row, because the particulars column is wider than the extracted line."""
        statement = parse(
            "01-07-2026 B/F 1,000.00\n"
            "Amazon Pay Groceries\n"
            "UPI/Amazon Pay/amazonpaygroce/You are pa/AXIS\n"
            "02-07-2026 691.00 309.00\n"
        )

        assert "Amazon Pay Groceries" in statement.transactions[0].description

    def test_particulars_printed_inline_are_captured(self) -> None:
        statement = parse(
            "01-07-2026 B/F 1,000.00\n"
            "02-07-2026 UPI/Amazon Ind/amazon@yapl/You are pa/YES BANK 691.00 309.00\n"
        )

        assert "amazon@yapl" in statement.transactions[0].description

    def test_a_reference_tail_stays_with_its_own_row(self) -> None:
        """Plumbing printed *after* a row must not become the next row's
        merchant name — that would misfile the following transaction."""
        statement = parse(
            "01-07-2026 B/F 1,000.00\n"
            "FIRST MERCHANT\n"
            "02-07-2026 100.00 900.00\n"
            "BANK/000000000000/APL0000000000/\n"
            "SECOND MERCHANT\n"
            "03-07-2026 200.00 700.00\n"
        )

        first, second = statement.transactions
        assert "FIRST MERCHANT" in first.description
        assert "BANK/000000000000" in first.description
        assert "BANK/000000000000" not in second.description
        assert second.description.startswith("SECOND MERCHANT")


class TestHeaderIsNotMistakenForTransactions:
    def test_the_account_summary_is_skipped(self) -> None:
        """The forty-odd lines of summary above the table contain amounts that
        would otherwise be read as transactions."""
        statement = ICICIBankStatementParser().parse(
            FakeFile(
                "ICICI Bank Limited\n"
                "Savings Account Balance 4,73,446.03\n"
                "TOTAL 4,73,446.03\n"
                "Savings A/c XXXXXXXX0136 4,73,446.03 Registered\n"
                + HEADER
                + "01-07-2026 B/F 1,000.00\nSHOP\n02-07-2026 250.00 750.00\n"
            )
        )

        assert len(statement.transactions) == 1

    def test_page_furniture_is_ignored(self) -> None:
        statement = parse(
            "01-07-2026 B/F 1,000.00\n"
            "SHOP\n"
            "02-07-2026 250.00 750.00\n"
            "Page 1 of 6 M-89217283-36487\n"
            "This is a computer generated statement and does not require signature.\n"
        )

        assert len(statement.transactions) == 1
        assert "Page 1 of 6" not in statement.transactions[0].description


class TestDetection:
    def test_a_savings_statement_is_recognised(self) -> None:
        assert ICICIBankStatementParser.can_parse(ParsedFile(path=SAVINGS)) == Confidence.STRONG

    def test_it_declines_a_credit_card_statement(self) -> None:
        assert ICICIBankStatementParser.can_parse(ParsedFile(path=CREDIT_CARD)) == Confidence.NONE

    def test_the_card_parser_declines_a_savings_statement(self) -> None:
        """The two ICICI parsers must not compete for each other's files."""
        assert ICICICreditCardParser.can_parse(ParsedFile(path=SAVINGS)) == Confidence.NONE

    def test_a_non_icici_statement_is_declined(self) -> None:
        assert ICICIBankStatementParser.can_parse(FakeFile("HDFC BANK LTD\n")) == Confidence.NONE
