"""Turning an uploaded file into transactions."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from django.db import transaction as db_transaction

from apps.parsers.base import ParsedFile, ParsedStatement, ParseError
from apps.parsers.registry import parse_statement
from apps.rules.engine import categorise_transactions
from apps.sources.services import resolve_source
from apps.statements.models import Statement
from apps.transactions.models import Transaction, compute_dedupe_hash

logger = logging.getLogger(__name__)

__all__ = ["ImportResult", "import_statement"]


@dataclass(frozen=True)
class ImportResult:
    statement: Statement
    created: int
    duplicates: int

    @property
    def was_entirely_duplicate(self) -> bool:
        return self.created == 0 and self.duplicates > 0


def import_statement(
    statement: Statement,
    *,
    password: str | None = None,
    bank_slug: str | None = None,
) -> ImportResult:
    """Parse an uploaded statement and store its transactions.

    Records the outcome on the `Statement` either way: a failure needs to be
    visible in the UI with a message the user can act on, not swallowed.

    Idempotent by transaction: rows already imported from an overlapping period
    are counted as duplicates and skipped, so re-uploading is safe.
    """
    parsed_file = ParsedFile(
        path=Path(statement.file.path),
        filename=statement.original_filename,
        password=password,
    )

    try:
        parsed = parse_statement(parsed_file, bank_slug=bank_slug)
    except ParseError as exc:
        statement.status = Statement.Status.FAILED
        statement.error_message = str(exc)
        statement.save(update_fields=["status", "error_message", "updated_at"])
        return ImportResult(statement=statement, created=0, duplicates=0)
    except Exception as exc:
        # An unexpected failure is a bug, but the user still needs a usable
        # message rather than a 500 — and we need the traceback in the log.
        logger.exception("Unexpected error parsing statement %s", statement.pk)
        statement.status = Statement.Status.FAILED
        statement.error_message = (
            "Something went wrong reading this statement. If it opens correctly "
            "in your PDF or spreadsheet viewer, please report it as a bug."
        )
        statement.save(update_fields=["status", "error_message", "updated_at"])
        raise ParseError(statement.error_message) from exc

    return _persist(statement, parsed)


@db_transaction.atomic
def _persist(statement: Statement, parsed: ParsedStatement) -> ImportResult:
    household = statement.household
    source = resolve_source(household, parsed)

    incoming: dict[str, Transaction] = {}
    for parsed_transaction in parsed.transactions:
        dedupe_hash = compute_dedupe_hash(
            source_id=source.pk,
            txn_date=parsed_transaction.txn_date,
            amount=parsed_transaction.amount,
            description=parsed_transaction.description,
            reference=parsed_transaction.reference,
        )
        # A single file can itself repeat a row (some banks print a
        # continuation line twice). Last one wins; they are identical anyway.
        incoming[dedupe_hash] = Transaction(
            household=household,
            source=source,
            statement=statement,
            txn_date=parsed_transaction.txn_date,
            value_date=parsed_transaction.value_date,
            description=parsed_transaction.description,
            amount=parsed_transaction.amount,
            balance=parsed_transaction.balance,
            reference=parsed_transaction.reference or "",
            dedupe_hash=dedupe_hash,
        )

    already_present = set(
        Transaction.objects.for_household(household)
        .filter(dedupe_hash__in=incoming.keys())
        .values_list("dedupe_hash", flat=True)
    )

    to_create = [t for h, t in incoming.items() if h not in already_present]
    created = Transaction.objects.bulk_create(to_create)

    # Categorise inside the same transaction as the import, so a statement is
    # never briefly visible as a wall of uncategorised rows.
    if created:
        categorise_transactions(household, created)

    duplicates = len(incoming) - len(to_create)

    statement.status = Statement.Status.PARSED
    statement.source = source
    statement.bank_slug = parsed.bank_slug
    statement.statement_kind = parsed.statement_kind
    statement.period_start = parsed.period_start
    statement.period_end = parsed.period_end
    statement.transaction_count = len(to_create)
    statement.duplicate_count = duplicates
    statement.error_message = ""
    statement.save()

    return ImportResult(statement=statement, created=len(to_create), duplicates=duplicates)
