"""Tests for the shared parser utilities.

These matter more than any single parser: every bank depends on them, so a
regression here breaks statements nobody has looked at in months.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from apps.parsers.utils.amounts import is_amount, parse_amount, parse_signed_amount
from apps.parsers.utils.dates import find_dates, parse_date, parse_date_or_none
from apps.parsers.utils.tables import (
    clean_cell,
    detect_delimiter,
    drop_blank_rows,
    find_header_row,
    read_delimited,
)


class TestParseAmount:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("1234.00", "1234.00"),
            ("1,234.00", "1234.00"),
            # Indian lakh grouping — irregular, which is why commas are simply
            # dropped rather than a locale being inferred.
            ("1,20,450.00", "120450.00"),
            ("1,00,00,000.00", "10000000.00"),
            ("₹1,234.00", "1234.00"),
            ("Rs. 1,234.00", "1234.00"),
            ("INR 1,234.00", "1234.00"),
            ("  1,234.00  ", "1234.00"),
            ("0.00", "0.00"),
        ],
    )
    def test_positive_forms(self, text: str, expected: str) -> None:
        assert parse_amount(text) == Decimal(expected)

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("-1234.00", "-1234.00"),
            ("1234.00-", "-1234.00"),  # trailing minus, seen in older exports
            ("(1,234.00)", "-1234.00"),  # accounting parentheses
            ("1,234.00 Dr", "-1234.00"),  # Dr is money out
            ("1,234.00 DR", "-1234.00"),
            ("1,234.00 debit", "-1234.00"),
        ],
    )
    def test_negative_forms(self, text: str, expected: str) -> None:
        assert parse_amount(text) == Decimal(expected)

    def test_credit_marker_stays_positive(self) -> None:
        assert parse_amount("1,234.00 Cr") == Decimal("1234.00")

    def test_returns_decimal_not_float(self) -> None:
        assert isinstance(parse_amount("0.1"), Decimal)

    def test_float_input_keeps_the_printed_value(self) -> None:
        """Spreadsheet cells arrive as floats; str() avoids binary drift."""
        assert parse_amount(1234.56) == Decimal("1234.56")

    @pytest.mark.parametrize("text", ["", "   ", "abc", "N/A", "--", "12.34.56"])
    def test_rejects_non_amounts(self, text: str) -> None:
        with pytest.raises(ValueError):
            parse_amount(text)

    def test_is_amount(self) -> None:
        assert is_amount("1,234.00")
        assert not is_amount("NARRATION")


class TestParseSignedAmount:
    def test_debit_column_becomes_negative(self) -> None:
        assert parse_signed_amount(debit="1,500.00", credit="") == Decimal("-1500.00")

    def test_credit_column_stays_positive(self) -> None:
        assert parse_signed_amount(debit="", credit="2,000.00") == Decimal("2000.00")

    def test_zero_in_the_unused_column_is_not_a_conflict(self) -> None:
        """Many banks print 0.00 rather than leaving the cell blank."""
        assert parse_signed_amount(debit="0.00", credit="2,000.00") == Decimal("2000.00")
        assert parse_signed_amount(debit="1,500.00", credit="0.00") == Decimal("-1500.00")

    def test_both_columns_zero_is_zero(self) -> None:
        assert parse_signed_amount(debit="0.00", credit="0.00") == Decimal("0.00")

    def test_real_values_in_both_columns_is_an_error(self) -> None:
        with pytest.raises(ValueError, match="both"):
            parse_signed_amount(debit="100.00", credit="200.00")

    def test_neither_column_is_an_error(self) -> None:
        with pytest.raises(ValueError, match="neither"):
            parse_signed_amount(debit="", credit="")

    def test_debit_sign_is_normalised_even_if_printed_negative(self) -> None:
        """A debit column already showing a minus must not double-negate."""
        assert parse_signed_amount(debit="-1,500.00", credit="") == Decimal("-1500.00")


class TestParseDate:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("03/04/2024", date(2024, 4, 3)),
            ("03/04/24", date(2024, 4, 3)),
            ("03-04-2024", date(2024, 4, 3)),
            ("03-Apr-2024", date(2024, 4, 3)),
            ("03 Apr 2024", date(2024, 4, 3)),
            ("03 April 2024", date(2024, 4, 3)),
            ("03.04.2024", date(2024, 4, 3)),
            ("2024-04-03", date(2024, 4, 3)),
            ("Apr 03, 2024", date(2024, 4, 3)),
            ("03Apr2024", date(2024, 4, 3)),
        ],
    )
    def test_common_formats(self, text: str, expected: date) -> None:
        assert parse_date(text) == expected

    def test_day_comes_first(self) -> None:
        """The whole reason formats are explicit rather than guessed."""
        assert parse_date("05/03/2024") == date(2024, 3, 5)

    def test_whitespace_is_tolerated(self) -> None:
        assert parse_date("  03   Apr  2024 ") == date(2024, 4, 3)

    def test_two_digit_year_is_not_pushed_into_the_future(self) -> None:
        """Statements are historical: 68 means 1968, not 2068."""
        assert parse_date("01/01/68").year == 1968

    def test_passthrough_for_date_objects(self) -> None:
        assert parse_date(date(2024, 4, 3)) == date(2024, 4, 3)

    @pytest.mark.parametrize("text", ["", "not a date", "31/02/2024", "NARRATION"])
    def test_rejects_non_dates(self, text: str) -> None:
        with pytest.raises(ValueError):
            parse_date(text)

    def test_error_message_points_at_the_fix(self) -> None:
        with pytest.raises(ValueError, match="DEFAULT_FORMATS"):
            parse_date("2024|04|03")

    def test_parse_date_or_none_swallows_failures(self) -> None:
        assert parse_date_or_none("") is None
        assert parse_date_or_none(None) is None
        assert parse_date_or_none("03 Apr 2024") == date(2024, 4, 3)

    def test_find_dates_in_a_header_block(self) -> None:
        text = "Statement From : 01/04/2024 To : 30/04/2024\nGenerated 01 May 2024"
        assert find_dates(text) == [date(2024, 4, 1), date(2024, 4, 30), date(2024, 5, 1)]


class TestTables:
    def test_detects_tab_over_commas_in_amounts(self) -> None:
        """The case that matters: HDFC's tab-delimited export, whose amounts
        contain commas. Choosing comma here would shred every row."""
        text = (
            "Date\tNarration\tWithdrawal\n"
            "01/04/24\tSALARY CREDIT\t1,25,000.00\n"
            "03/04/24\tUPI-SWIGGY\t450.00\n"
        )
        assert detect_delimiter(text) == "\t"

    def test_detects_comma_for_plain_csv(self) -> None:
        text = "Date,Narration,Amount\n01/04/24,SALARY,1000.00\n03/04/24,SWIGGY,450.00\n"
        assert detect_delimiter(text) == ","

    def test_read_delimited_respects_quotes(self) -> None:
        rows = read_delimited('a,"b,c",d\n1,"2,3",4\n', ",")
        assert rows == [["a", "b,c", "d"], ["1", "2,3", "4"]]

    def test_clean_cell(self) -> None:
        assert clean_cell("  spaced   out  ") == "spaced out"
        assert clean_cell('"quoted"') == "quoted"
        assert clean_cell(None) == ""

    def test_find_header_row_skips_junk(self) -> None:
        rows = [
            ["HDFC BANK LTD"],
            [""],
            ["Account No : XXXXXXXX1234"],
            ["Date", "Narration", "Withdrawal Amt.", "Deposit Amt."],
            ["01/04/24", "SALARY", "0.00", "1000.00"],
        ]
        assert find_header_row(rows, ["date", "narration", "withdrawal"]) == 3

    def test_find_header_row_matches_substrings(self) -> None:
        rows = [["Txn Date", "Narration", "Withdrawal Amt."]]
        assert find_header_row(rows, ["date", "narration", "withdrawal"]) == 0

    def test_find_header_row_raises_when_absent(self) -> None:
        with pytest.raises(ValueError, match="no header row"):
            find_header_row([["a", "b"]], ["date", "narration"])

    def test_drop_blank_rows_removes_separators(self) -> None:
        rows = [["a", "b"], ["", ""], ["---", "---"], ["c", "d"]]
        assert drop_blank_rows(rows) == [["a", "b"], ["c", "d"]]
