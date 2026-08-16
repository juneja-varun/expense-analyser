from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import HouseholdScopedModel


class Source(HouseholdScopedModel):
    """An account or card that statements come from.

    Transactions hang off a source rather than off a bank, because a household
    routinely has several accounts at the same bank and the running balance
    only makes sense per account.

    `account_hint` is the masked tail a parser reads off the statement — never
    a full account number. It is what lets a second upload from the same
    account attach itself without the user picking anything.
    """

    class Kind(models.TextChoices):
        BANK = "bank", _("Bank account")
        CREDIT_CARD = "credit_card", _("Credit card")

    name = models.CharField(
        max_length=100,
        help_text='What the user calls it, e.g. "HDFC Salary" or "ICICI Amazon Pay".',
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    bank_slug = models.CharField(
        max_length=40,
        blank=True,
        help_text="Parser slug this source's statements use, e.g. 'hdfc'.",
    )
    account_hint = models.CharField(
        max_length=32,
        blank=True,
        help_text="Masked account or card tail, e.g. XXXXXXXX1234. Never the full number.",
    )
    currency = models.CharField(max_length=3, default="INR")
    is_archived = models.BooleanField(
        default=False,
        help_text="Closed accounts stay for their history but are hidden from new uploads.",
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["household", "bank_slug", "account_hint"],
                condition=~models.Q(account_hint=""),
                name="unique_source_per_account_hint",
            ),
        ]
        indexes = [models.Index(fields=["household", "is_archived"])]

    def __str__(self) -> str:
        if self.account_hint:
            return f"{self.name} ({self.account_hint})"
        return self.name

    @property
    def is_credit_card(self) -> bool:
        return self.kind == self.Kind.CREDIT_CARD
