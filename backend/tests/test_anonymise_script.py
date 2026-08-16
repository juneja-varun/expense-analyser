"""Tests for scripts/anonymise_statement.py.

This tool is the difference between a contributor committing a usable fixture
and committing their own bank details, so its failure modes are worth pinning
down. Both regressions below were real bugs found in review.
"""

from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "anonymise_statement.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("anonymise_statement", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


anonymise_statement = _load()


# Deliberately "dirty" input for the anonymiser. Every value is invented, and
# the identifiers use reserved or obviously-fake forms (example.com, a PAN of
# all Zs) so that nothing here can collide with a real person's details — this
# file is public, and a plausible-looking gmail address or PAN would be exactly
# the kind of thing this project exists to keep out of repositories.
DIRTY = """SOME BANK LTD
Name : RAJESH KUMAR SHARMA
Address : 42 MG Road, Indiranagar
City : Bengaluru
Cust ID : 887766554
Account No : 50100234567890
IFSC : HDFC0001234
Email : rajesh.sharma@example.com
Phone : 9876543210
PAN : ZZZZZ0000Z

Date,Narration,Withdrawal,Deposit,Balance
01/04/24,SALARY CREDIT,0.00,125000.00,132450.75
03/04/24,UPI-SWIGGY,450.00,0.00,132000.75
"""


@pytest.fixture
def cleaned() -> str:
    return anonymise_statement.anonymise(DIRTY)


class TestAnonymise:
    @pytest.mark.parametrize(
        "secret",
        [
            "RAJESH KUMAR SHARMA",
            "42 MG Road",
            "Bengaluru",
            "887766554",
            "50100234567890",
            "HDFC0001234",
            "rajesh.sharma@example.com",
            "9876543210",
            "ZZZZZ0000Z",
        ],
    )
    def test_removes_personal_data(self, cleaned: str, secret: str) -> None:
        assert secret not in cleaned

    def test_keeps_the_last_four_of_an_account_number(self, cleaned: str) -> None:
        """Parsers match uploads to accounts on the last four digits."""
        assert "XXXXXXXXXX7890" in cleaned

    def test_substitutes_documented_placeholders(self, cleaned: str) -> None:
        assert "TEST USER" in cleaned
        assert "test@example.com" in cleaned
        assert "BANK0000000" in cleaned
        assert "ABCDE1234F" in cleaned

    def test_labelled_field_substitution_is_not_mangled(self, cleaned: str) -> None:
        """Regression: a `\\1000000000` replacement is read as group 10.

        The symptom was `Cust ID : 887766554` becoming `@0000000` — the label
        destroyed along with the value.
        """
        assert "Cust ID : 000000000" in cleaned
        assert "@0000000" not in cleaned

    def test_placeholder_phone_is_not_re_masked(self, cleaned: str) -> None:
        """Regression: digit masking ran last and ate its own placeholder,
        turning the substituted 9000000000 into XXXXXX0000."""
        assert "Phone : 9000000000" in cleaned
        assert "XXXXXX0000" not in cleaned

    def test_preserves_the_transaction_table(self, cleaned: str) -> None:
        """The layout is the only reason the fixture exists."""
        assert "Date,Narration,Withdrawal,Deposit,Balance" in cleaned
        assert "SALARY CREDIT" in cleaned
        assert "01/04/24" in cleaned


class TestJitter:
    def test_scales_grouped_and_ungrouped_amounts_alike(self) -> None:
        """Regression: the amount pattern required comma grouping, so plain
        125000.00 was left at its real value while 1,234.00 was scaled."""
        jittered = anonymise_statement.jitter_amounts("125000.00 and 1,234.00", seed=1)
        assert "125000.00" not in jittered
        assert "1,234.00" not in jittered

    def test_running_balances_stay_consistent(self) -> None:
        """One factor for the whole file, so balance arithmetic still holds —
        parser tests frequently assert on it."""
        text = anonymise_statement.jitter_amounts(
            "opening 132450.75 spend 450.00 closing 132000.75", seed=7
        )
        opening, spend, closing = (
            Decimal(value.replace(",", ""))
            for value in text.replace("opening ", "")
            .replace(" spend ", " ")
            .replace(" closing ", " ")
            .split()
        )
        assert opening - spend == closing

    def test_is_deterministic_for_a_given_seed(self) -> None:
        assert anonymise_statement.jitter_amounts("1,234.00", seed=3) == (
            anonymise_statement.jitter_amounts("1,234.00", seed=3)
        )


class TestPdfRefusal:
    def test_refuses_to_rewrite_a_pdf(self, tmp_path: Path, capsys) -> None:
        """Half-cleaning a PDF is worse than not trying: the text layer,
        metadata and embedded fonts all carry traces."""
        source = tmp_path / "statement.pdf"
        source.write_bytes(b"%PDF-1.4\nnot really a pdf\n")

        exit_code = anonymise_statement.main([str(source), "--out", str(tmp_path / "out.pdf")])

        assert exit_code == 2
        assert not (tmp_path / "out.pdf").exists()
        assert "does not rewrite PDFs" in capsys.readouterr().err
