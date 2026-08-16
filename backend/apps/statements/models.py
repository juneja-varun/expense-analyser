from __future__ import annotations

import uuid
from pathlib import Path

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import HouseholdScopedModel


def statement_upload_path(instance: Statement, filename: str) -> str:
    """Store uploads under an unguessable per-household path.

    The filename a user uploads often contains their account number, so it is
    replaced rather than preserved.
    """
    suffix = Path(filename).suffix.lower()
    return f"statements/{instance.household_id}/{uuid.uuid4().hex}{suffix}"


class Statement(HouseholdScopedModel):
    """One uploaded statement file, and the outcome of parsing it.

    Kept after import for provenance — when a transaction looks wrong, the
    first question is always "what did the file actually say".
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        PARSED = "parsed", _("Parsed")
        FAILED = "failed", _("Failed")

    file = models.FileField(upload_to=statement_upload_path)
    original_filename = models.CharField(max_length=255)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)

    source = models.ForeignKey(
        "sources.Source",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="statements",
    )
    bank_slug = models.CharField(max_length=40, blank=True)
    statement_kind = models.CharField(max_length=16, blank=True)

    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)

    transaction_count = models.PositiveIntegerField(
        default=0, help_text="Transactions created by this upload."
    )
    duplicate_count = models.PositiveIntegerField(
        default=0,
        help_text="Rows already present from an earlier upload, skipped rather than duplicated.",
    )
    error_message = models.TextField(
        blank=True,
        help_text="Shown to the user when parsing fails, so it must be actionable.",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["household", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.original_filename} ({self.status})"

    @property
    def was_entirely_duplicate(self) -> bool:
        """A re-upload of a period already imported.

        Worth telling the user explicitly — otherwise a successful upload that
        adds nothing looks like a failure.
        """
        return (
            self.status == self.Status.PARSED
            and self.transaction_count == 0
            and self.duplicate_count > 0
        )
