"""API response-shape guarantees.

Both of these were found by driving the running server rather than the test
suite — the app worked, but the JSON contract was inconsistent in ways that
would bite any client.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.categories.models import Category
from apps.sources.models import Source
from apps.transactions.models import Transaction

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return User.objects.create_user(email="asha@example.com", password="corr3ct-h0rse-b4ttery")


@pytest.fixture
def client(user) -> APIClient:
    api = APIClient()
    api.force_authenticate(user=user)
    return api


@pytest.fixture
def source(user):
    return Source.objects.create(
        household=user.default_household, name="HDFC", kind=Source.Kind.BANK
    )


def make_transaction(user, source, **kwargs):
    fields = {
        "txn_date": date(2024, 4, 3),
        "description": "UPI-SWIGGY-PAY",
        "amount": Decimal("-450.00"),
        **kwargs,
    }
    return Transaction.objects.create(household=user.default_household, source=source, **fields)


class TestFieldsAreAlwaysPresent:
    def test_uncategorised_transaction_still_has_category_fields(
        self, client, user, source
    ) -> None:
        """Regression: `source="category.full_name"` made DRF drop the key
        entirely when the category was null, so uncategorised and categorised
        transactions had different shapes."""
        make_transaction(user, source)

        row = client.get("/api/transactions/").data["results"][0]

        assert "category_name" in row
        assert "category_colour" in row
        assert row["category_name"] is None
        assert row["category"] is None

    def test_categorised_transaction_reports_its_full_path(self, client, user, source) -> None:
        delivery = Category.objects.for_household(user.default_household).get(name="Food Delivery")
        make_transaction(user, source, category=delivery)

        row = client.get("/api/transactions/").data["results"][0]

        assert row["category_name"] == "Food & Dining → Eating Out → Food Delivery"


class TestMoneyIsNeverAFloat:
    """Money crosses the wire as a decimal string, never a JSON float.

    Regression: the summary endpoint returned bare `Decimal` values, which DRF
    renders as floats — the precision loss the rest of the codebase is careful
    to avoid.
    """

    def test_amount_is_a_string(self, client, user, source) -> None:
        make_transaction(user, source)

        payload = json.loads(client.get("/api/transactions/").content)

        assert payload["results"][0]["amount"] == "-450.00"

    @pytest.mark.parametrize("field", ["spent", "received", "net"])
    def test_summary_totals_are_strings(self, client, user, source, field: str) -> None:
        make_transaction(user, source)
        make_transaction(user, source, description="SALARY", amount=Decimal("125000.00"))

        payload = json.loads(client.get("/api/transactions/summary/").content)

        assert isinstance(payload[field], str), f"{field} came back as {type(payload[field])}"

    def test_summary_totals_are_exact(self, client, user, source) -> None:
        make_transaction(user, source, amount=Decimal("-0.10"))
        make_transaction(user, source, description="B", amount=Decimal("-0.20"))

        payload = json.loads(client.get("/api/transactions/summary/").content)

        # 0.1 + 0.2 is the canonical float-precision trap.
        assert Decimal(payload["spent"]) == Decimal("0.30")
