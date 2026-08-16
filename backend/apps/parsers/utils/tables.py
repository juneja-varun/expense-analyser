"""Finding the actual transaction table under a pile of header junk.

Indian statement exports rarely start with the data. A typical HDFC download is
twenty lines of account summary, then a delimited table, then a footer of
disclaimers. These helpers locate the table without hardcoding "skip 20 lines",
which breaks the moment the bank adds a line to the header.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterator, Sequence

__all__ = [
    "clean_cell",
    "detect_delimiter",
    "drop_blank_rows",
    "find_header_row",
    "normalise_row",
    "read_delimited",
    "rows_after_header",
]

_MULTISPACE = re.compile(r"\s+")

# Order matters: tab first, because bank exports that call themselves .xls are
# very often tab-delimited text, and their descriptions contain commas.
_CANDIDATE_DELIMITERS = ("\t", "|", ";", ",")


def detect_delimiter(text: str, sample_lines: int = 50) -> str:
    """Guess the delimiter by which candidate yields the most consistent columns.

    More reliable than csv.Sniffer on statement files, whose header junk has a
    different shape from the table and throws the sniffer off.
    """
    lines = [ln for ln in text.splitlines()[:sample_lines] if ln.strip()]
    if not lines:
        return ","

    best, best_score = ",", 0.0
    for delimiter in _CANDIDATE_DELIMITERS:
        counts = [ln.count(delimiter) for ln in lines]
        populated = [c for c in counts if c > 0]
        if len(populated) < 2:
            continue
        # Reward many columns appearing consistently across many lines.
        most_common = max(set(populated), key=populated.count)
        consistency = populated.count(most_common) / len(lines)
        score = consistency * most_common
        if score > best_score:
            best, best_score = delimiter, score
    return best


def read_delimited(text: str, delimiter: str | None = None) -> list[list[str]]:
    """Parse delimited text into rows, honouring quoted fields."""
    if delimiter is None:
        delimiter = detect_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    return [[clean_cell(cell) for cell in row] for row in reader]


def clean_cell(value: str | None) -> str:
    """Collapse whitespace and strip surrounding quotes."""
    if value is None:
        return ""
    text = _MULTISPACE.sub(" ", str(value)).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


def normalise_row(row: Sequence[str | None]) -> list[str]:
    return [clean_cell(cell) for cell in row]


def find_header_row(
    rows: Sequence[Sequence[str | None]],
    required: Sequence[str],
    *,
    minimum_matches: int | None = None,
) -> int:
    """Index of the row that looks like the table header.

    Matching is case- and whitespace-insensitive and substring-based, so
    "Withdrawal Amt." matches a required "withdrawal".

    >>> rows = [["HDFC BANK"], [""], ["Date", "Narration", "Withdrawal Amt."]]
    >>> find_header_row(rows, ["date", "narration", "withdrawal"])
    2

    Raises ValueError if no row matches — parsers should turn that into a
    ParseError naming what was expected, since it usually means the bank
    changed its layout.
    """
    needed = minimum_matches if minimum_matches is not None else len(required)
    wanted = [r.lower() for r in required]

    for index, row in enumerate(rows):
        cells = [clean_cell(c).lower() for c in row]
        if not any(cells):
            continue
        matches = sum(1 for want in wanted if any(want in cell for cell in cells))
        if matches >= needed:
            return index

    raise ValueError(
        f"no header row containing {list(required)} found in the first " f"{len(rows)} rows"
    )


def rows_after_header(
    rows: Sequence[Sequence[str | None]],
    required: Sequence[str],
    *,
    minimum_matches: int | None = None,
) -> tuple[list[str], Iterator[list[str]]]:
    """Locate the header and return it alongside the data rows that follow."""
    index = find_header_row(rows, required, minimum_matches=minimum_matches)
    header = normalise_row(rows[index])
    body = (normalise_row(row) for row in rows[index + 1 :])
    return header, body


def drop_blank_rows(rows: Iterator[list[str]] | Sequence[list[str]]) -> list[list[str]]:
    """Remove rows that are entirely empty or made only of separator characters."""
    kept: list[list[str]] = []
    for row in rows:
        cells = [clean_cell(c) for c in row]
        if not any(cells):
            continue
        if all(not c or set(c) <= set("-_=* ") for c in cells):
            continue
        kept.append(cells)
    return kept
