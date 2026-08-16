"""Turning a ParsedStatement into stable JSON, for golden-file tests.

Dates become ISO strings and Decimals become strings (never floats, which would
make the golden files depend on binary rounding). Key order is fixed so a diff
shows what actually changed.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any

from apps.parsers.base import ParsedStatement, ParsedTransaction

__all__ = ["statement_to_dict", "statement_to_json"]


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _date(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _transaction_to_dict(transaction: ParsedTransaction) -> dict[str, Any]:
    return {
        "txn_date": _date(transaction.txn_date),
        "value_date": _date(transaction.value_date),
        "description": transaction.description,
        "amount": _decimal(transaction.amount),
        "balance": _decimal(transaction.balance),
        "reference": transaction.reference,
    }


def statement_to_dict(statement: ParsedStatement) -> dict[str, Any]:
    """A comparable dict for a parsed statement.

    `raw` is deliberately excluded: it exists for debugging a mis-parse and
    would make every golden file churn whenever a column is renamed.
    """
    return {
        "bank_slug": statement.bank_slug,
        "statement_kind": statement.statement_kind,
        "source_hint": statement.source_hint,
        "period_start": _date(statement.period_start),
        "period_end": _date(statement.period_end),
        "opening_balance": _decimal(statement.opening_balance),
        "closing_balance": _decimal(statement.closing_balance),
        "transaction_count": len(statement.transactions),
        "total_debits": _decimal(statement.total_debits),
        "total_credits": _decimal(statement.total_credits),
        "transactions": [_transaction_to_dict(t) for t in statement.transactions],
    }


def statement_to_json(statement: ParsedStatement) -> str:
    return json.dumps(statement_to_dict(statement), indent=2, ensure_ascii=False) + "\n"
