from __future__ import annotations

import hashlib
import re
from decimal import Decimal

from django.db import models

from apps.common.models import HouseholdScopedModel

# Volatile fragments that make the "same" transaction look different between
# two exports of an overlapping period: statement-run timestamps, sequence
# numbers appended by the export, and runs of whitespace.
_WHITESPACE = re.compile(r"\s+")


def normalise_description(description: str) -> str:
    """Reduce a narration to a stable form for hashing.

    Only used for the dedupe hash — the raw description is always stored and
    displayed unchanged, because the user needs to recognise their own
    transaction and the categorisation rules match on the original string.
    """
    return _WHITESPACE.sub(" ", description).strip().upper()


def compute_dedupe_hash(
    *,
    source_id: int,
    txn_date,
    amount: Decimal,
    description: str,
    reference: str | None,
) -> str:
    """A stable identity for one transaction.

    Users routinely download overlapping date ranges, so re-uploading must be a
    no-op rather than doubling their spending. The reference number is included
    when the bank provides one — it is the only field that reliably separates
    two genuinely distinct payments of the same amount to the same payee on the
    same day.
    """
    parts = [
        str(source_id),
        txn_date.isoformat(),
        f"{amount:.2f}",
        normalise_description(description),
        (reference or "").strip().upper(),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


class Transaction(HouseholdScopedModel):
    """One line of a statement, after parsing.

    `amount` is signed, negative for money leaving the account — the parsers
    normalise this, so nothing here needs to know whether it came from a bank
    statement or a card statement.
    """

    source = models.ForeignKey(
        "sources.Source",
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    statement = models.ForeignKey(
        "statements.Statement",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions",
        help_text="The upload this arrived in. Kept for provenance; nulled if it is deleted.",
    )
    category = models.ForeignKey(
        "categories.Category",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions",
    )

    txn_date = models.DateField(db_index=True)
    value_date = models.DateField(null=True, blank=True)
    description = models.TextField(help_text="The narration exactly as the bank printed it.")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    balance = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    reference = models.CharField(max_length=64, blank=True)

    notes = models.TextField(blank=True)
    is_categorised_by_user = models.BooleanField(
        default=False,
        help_text=(
            "Set when a person picks the category, so re-running the rules "
            "never overrides their choice."
        ),
    )

    dedupe_hash = models.CharField(max_length=64, editable=False)

    class Meta:
        ordering = ["-txn_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["household", "dedupe_hash"],
                name="unique_transaction_per_household",
            ),
        ]
        indexes = [
            models.Index(fields=["household", "-txn_date"]),
            models.Index(fields=["household", "category"]),
            models.Index(fields=["source", "-txn_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.txn_date} {self.amount} {self.description[:40]}"

    def save(self, *args, **kwargs) -> None:
        if not self.dedupe_hash:
            self.dedupe_hash = compute_dedupe_hash(
                source_id=self.source_id,
                txn_date=self.txn_date,
                amount=self.amount,
                description=self.description,
                reference=self.reference,
            )
        super().save(*args, **kwargs)

    @property
    def is_debit(self) -> bool:
        return self.amount < 0

    @property
    def absolute_amount(self) -> Decimal:
        return abs(self.amount)
