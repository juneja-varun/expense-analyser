"""Guards against a statement being handed to the wrong parser.

This is the worst failure mode the parser system has. A wrong parser does not
crash — it produces confident, plausible, wrong numbers. Found when an ICICI
*savings* statement was routed to the ICICI *credit card* parser: it read the
closing balance as the transaction amount and turned a ₹125,000 salary credit
into a ₹177,340 debit, reporting success throughout.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.parsers.banks.icici.parser import ICICICreditCardParser
from apps.parsers.base import BaseParser, Confidence, NoParserFound, ParsedFile
from apps.parsers.registry import MIN_AUTO_DETECT, detect_parser, discover_parsers, rank_parsers

ICICI_BANK_STATEMENT = """ICICI Bank Limited
Statement of Transactions in Savings Account
Account Number : XXXXXXXX5678
Period : 01-04-2024 to 30-04-2024

Date Mode Particulars Deposits Withdrawals Balance
03-04-2024 UPI UPI/SWIGGY/409412345678 0.00 450.00 52,340.15
05-04-2024 NEFT SALARY TESTCORP 125000.00 0.00 177,340.15
"""


class FakeFile:
    """A ParsedFile stand-in, so these cases need no binary fixture."""

    def __init__(self, text: str, extension: str = "pdf") -> None:
        self.text = text
        self.head = text[:4096]
        self.extension = extension
        self.filename = f"statement.{extension}"

    def contains_any(self, *needles: str) -> bool:
        return any(needle.lower() in self.text.lower() for needle in needles)


class TestIciciBankStatementIsNotACardStatement:
    def test_the_card_parser_declines_a_savings_statement(self) -> None:
        assert ICICICreditCardParser.can_parse(FakeFile(ICICI_BANK_STATEMENT)) == Confidence.NONE

    def test_it_still_recognises_a_real_card_statement(self) -> None:
        card = FakeFile(
            "ICICI Bank Limited\nCredit Card Statement\n"
            "Card Number: XXXX XXXX XXXX 4321\nPayment Due Date: 22/04/2024\n"
        )
        assert ICICICreditCardParser.can_parse(card) == Confidence.STRONG

    def test_nothing_claims_an_icici_savings_statement_yet(self) -> None:
        """Until an ICICI bank parser exists, the honest answer is "we can't
        read this" — not a wrong one."""
        with pytest.raises(NoParserFound):
            detect_parser(FakeFile(ICICI_BANK_STATEMENT))


class TestWeakMatchesAreNotDispatched:
    def test_weak_confidence_is_below_the_auto_dispatch_bar(self) -> None:
        assert Confidence.WEAK < MIN_AUTO_DETECT

    def test_a_weak_only_match_asks_rather_than_guesses(self, monkeypatch) -> None:
        class Vague(BaseParser):
            bank_slug = "vague"
            display_name = "Vague Bank"
            statement_kind = "bank"
            file_formats = ["csv"]

            @classmethod
            def can_parse(cls, file) -> Confidence:
                return Confidence.WEAK

            def parse(self, file):  # pragma: no cover - must never be reached
                raise AssertionError("a WEAK match must not be parsed automatically")

        monkeypatch.setattr(
            "apps.parsers.registry.discover_parsers", lambda: (*discover_parsers(), Vague)
        )
        file = FakeFile("something vaguely tabular\n", extension="csv")

        # It is still offered as a candidate — the UI can present it.
        assert [p for p, _ in rank_parsers(file)] == [Vague]

        with pytest.raises(NoParserFound, match="(?i)pick the bank manually"):
            detect_parser(file)

    def test_a_likely_match_is_dispatched(self, monkeypatch) -> None:
        """The bar must not be so high that ordinary detection stops working."""

        class Confident(BaseParser):
            bank_slug = "confident"
            display_name = "Confident Bank"
            statement_kind = "bank"
            file_formats = ["csv"]

            @classmethod
            def can_parse(cls, file) -> Confidence:
                return Confidence.LIKELY

            def parse(self, file):  # pragma: no cover
                raise NotImplementedError

        monkeypatch.setattr(
            "apps.parsers.registry.discover_parsers", lambda: (*discover_parsers(), Confident)
        )
        assert detect_parser(FakeFile("whatever\n", extension="csv")) is Confident


class TestBundledFixturesStillDispatch:
    """The bar must not break the parsers that already worked."""

    @pytest.mark.parametrize(
        ("fixture", "expected_slug"),
        [
            ("hdfc/tests/fixtures/hdfc_savings_2024_04.xls", "hdfc"),
            ("icici/tests/fixtures/icici_credit_card_2024_04.pdf", "icici"),
        ],
    )
    def test_real_fixtures_are_still_detected(self, fixture: str, expected_slug: str) -> None:
        path = Path(__file__).resolve().parent.parent / "banks" / fixture
        assert detect_parser(ParsedFile(path=path)).bank_slug == expected_slug
