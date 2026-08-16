"""Parsing Indian statement dates.

Formats are matched from an explicit list rather than guessed. `dateutil` would
be shorter, but `03/04/2024` is genuinely ambiguous and a wrong guess produces
transactions silently filed in the wrong month — the kind of bug a user only
notices three statements later.

**Day comes first.** Indian statements are DD/MM without exception; a parser
that needs MM/DD should say so explicitly via `formats=`.
"""

from __future__ import annotations

import re
from datetime import date, datetime

__all__ = ["DEFAULT_FORMATS", "find_dates", "parse_date", "parse_date_or_none"]

DEFAULT_FORMATS: tuple[str, ...] = (
    "%d/%m/%Y",  # 03/04/2024
    "%d/%m/%y",  # 03/04/24
    "%d-%m-%Y",  # 03-04-2024
    "%d-%m-%y",  # 03-04-24
    "%d-%b-%Y",  # 03-Apr-2024
    "%d-%b-%y",  # 03-Apr-24
    "%d %b %Y",  # 03 Apr 2024
    "%d %b, %Y",  # 03 Apr, 2024
    "%d %B %Y",  # 03 April 2024
    "%d.%m.%Y",  # 03.04.2024
    "%d.%m.%y",  # 03.04.24
    "%Y-%m-%d",  # 2024-04-03 (ISO, and some CSV exports)
    "%b %d, %Y",  # Apr 03, 2024 (some card statements)
    "%d%b%Y",  # 03Apr2024
)

# Two-digit years: statements are historical, so a year that would land in the
# future almost certainly belongs to the previous century.
_PIVOT_YEAR = 60

_WHITESPACE = re.compile(r"\s+")

_DATE_PATTERN = re.compile(
    r"\b("
    r"\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}"
    r"|\d{1,2}[\s\-]?[A-Za-z]{3,9}[\s\-,]?\s?\d{2,4}"
    r"|\d{4}-\d{2}-\d{2}"
    r")\b"
)


def _normalise(value: str) -> str:
    return _WHITESPACE.sub(" ", str(value).strip())


def parse_date(
    value: str | date | datetime,
    formats: tuple[str, ...] | list[str] = DEFAULT_FORMATS,
) -> date:
    """Parse a statement date. Raises ValueError if no format matches.

    >>> parse_date("03 Apr 2024")
    datetime.date(2024, 4, 3)
    >>> parse_date("03/04/24")
    datetime.date(2024, 4, 3)
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = _normalise(value)
    if not text:
        raise ValueError("empty date")

    for fmt in formats:
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if "%y" in fmt and "%Y" not in fmt:
            return _fix_two_digit_year(parsed).date()
        return parsed.date()

    raise ValueError(
        f"could not read {value!r} as a date. "
        f"If your bank uses a format not in DEFAULT_FORMATS, pass formats= "
        f"explicitly, and add it to dates.py if other banks share it."
    )


def _fix_two_digit_year(parsed: datetime) -> datetime:
    """strptime maps 69-99 to 1969-1999 and 00-68 to 2000-2068.

    That is wrong for statements: a "68" is far more likely 1968 than 2068. We
    keep strptime's mapping but pull implausible future years back a century.
    """
    if parsed.year > date.today().year + 1:
        return parsed.replace(year=parsed.year - 100)
    return parsed


def parse_date_or_none(
    value: str | date | datetime | None,
    formats: tuple[str, ...] | list[str] = DEFAULT_FORMATS,
) -> date | None:
    """As `parse_date`, but returns None instead of raising.

    For optional columns such as value date, which banks often leave blank.
    """
    if value is None:
        return None
    try:
        return parse_date(value, formats)
    except (ValueError, TypeError):
        return None


def find_dates(text: str, formats: tuple[str, ...] = DEFAULT_FORMATS) -> list[date]:
    """Every date in a block of text, in order of appearance.

    Handy for pulling a statement period out of a PDF header.
    """
    found: list[date] = []
    for match in _DATE_PATTERN.finditer(text):
        parsed = parse_date_or_none(match.group(1), formats)
        if parsed is not None:
            found.append(parsed)
    return found
