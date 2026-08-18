from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.categories.models import Category
from apps.insights.services import monthly_totals, spend_by_category
from apps.sources.models import Source
from apps.transactions.models import Transaction

pytestmark = pytest.mark.django_db

APRIL = date(2024, 4, 1)


@pytest.fixture
def user():
    return User.objects.create_user(email="asha@example.com", password="corr3ct-h0rse-b4ttery")


@pytest.fixture
def household(user):
    return user.default_household


@pytest.fixture
def client(user) -> APIClient:
    api = APIClient()
    api.force_authenticate(user=user)
    return api


@pytest.fixture
def source(household):
    return Source.objects.create(household=household, name="HDFC", kind=Source.Kind.BANK)


def category(household, name: str) -> Category:
    return Category.objects.for_household(household).get(name=name)


def txn(household, source, amount: str, category_obj=None, when: date = APRIL) -> Transaction:
    return Transaction.objects.create(
        household=household,
        source=source,
        category=category_obj,
        txn_date=when,
        description=f"TXN {amount}",
        amount=Decimal(amount),
    )


class TestSpendByCategory:
    def test_rolls_children_up_into_their_top_level_category(self, household, source) -> None:
        """Forty leaf categories make an unreadable chart, and "where did my
        money go" is a top-level question."""
        txn(household, source, "-450.00", category(household, "Food Delivery"))
        txn(household, source, "-2000.00", category(household, "Groceries"))
        txn(household, source, "-3000.00", category(household, "Fuel"))

        rows = spend_by_category(household, APRIL)

        assert [(r.name, r.amount) for r in rows] == [
            ("Food & Dining", Decimal("2450.00")),
            ("Transport", Decimal("3000.00")),
        ][::-1]  # largest first

    def test_largest_first(self, household, source) -> None:
        txn(household, source, "-100.00", category(household, "Food Delivery"))
        txn(household, source, "-900.00", category(household, "Fuel"))

        rows = spend_by_category(household, APRIL)

        assert [r.name for r in rows] == ["Transport", "Food & Dining"]

    def test_income_is_excluded(self, household, source) -> None:
        """A spend chart including salary would be meaningless."""
        txn(household, source, "-450.00", category(household, "Food Delivery"))
        txn(household, source, "125000.00", category(household, "Salary"))

        rows = spend_by_category(household, APRIL)

        assert [r.name for r in rows] == ["Food & Dining"]

    def test_uncategorised_spend_is_shown_not_hidden(self, household, source) -> None:
        """Hiding it would make the chart total disagree with the transaction
        list, which is worse than an ugly slice."""
        txn(household, source, "-450.00", category(household, "Food Delivery"))
        txn(household, source, "-999.00", None)

        rows = spend_by_category(household, APRIL)

        assert ("Uncategorised", Decimal("999.00")) in [(r.name, r.amount) for r in rows]

    def test_other_months_are_excluded(self, household, source) -> None:
        txn(household, source, "-450.00", category(household, "Food Delivery"))
        txn(household, source, "-800.00", category(household, "Food Delivery"), date(2024, 5, 1))

        rows = spend_by_category(household, APRIL)

        assert rows[0].amount == Decimal("450.00")

    def test_refunds_reduce_the_total(self, household, source) -> None:
        delivery = category(household, "Food Delivery")
        txn(household, source, "-450.00", delivery)
        txn(household, source, "150.00", delivery)

        rows = spend_by_category(household, APRIL)

        assert rows[0].amount == Decimal("300.00")

    def test_a_month_with_no_spend_is_empty(self, household) -> None:
        assert spend_by_category(household, APRIL) == []


class TestMonthlyTrend:
    def test_quiet_months_are_filled_with_zeroes(self, household, source) -> None:
        """A missing month would collapse the x-axis and misrepresent the trend."""
        rows = monthly_totals(household, months=6)

        assert len(rows) == 6
        assert all(r.spent == Decimal("0.00") for r in rows)

    def test_months_are_oldest_first(self, household) -> None:
        rows = monthly_totals(household, months=4)

        assert [r.month for r in rows] == sorted(r.month for r in rows)

    def test_totals_split_spend_from_income(self, household, source) -> None:
        today = date.today().replace(day=1)
        txn(household, source, "-450.00", None, today)
        txn(household, source, "125000.00", None, today)

        current = next(r for r in monthly_totals(household, months=3) if r.month == today)

        assert current.spent == Decimal("450.00")
        assert current.received == Decimal("125000.00")
        assert current.net == Decimal("124550.00")


class TestInsightsApi:
    def test_spend_by_category_endpoint(self, client, household, source) -> None:
        txn(household, source, "-450.00", category(household, "Food Delivery"))

        response = client.get("/api/insights/spend_by_category/?month=2024-04")

        assert response.status_code == 200
        assert response.data["total"] == "450.00"
        assert response.data["categories"][0]["name"] == "Food & Dining"

    def test_monthly_trend_endpoint(self, client, household) -> None:
        response = client.get("/api/insights/monthly_trend/?months=6")

        assert response.status_code == 200
        assert len(response.data["months"]) == 6

    def test_trend_length_is_clamped(self, client, household) -> None:
        """An unbounded `months` would let one request scan the whole table."""
        assert len(client.get("/api/insights/monthly_trend/?months=500").data["months"]) == 36
        assert len(client.get("/api/insights/monthly_trend/?months=0").data["months"]) == 1

    def test_a_nonsense_months_value_falls_back_to_the_default(self, client, household) -> None:
        assert len(client.get("/api/insights/monthly_trend/?months=lots").data["months"]) == 12

    def test_money_crosses_the_wire_as_strings(self, client, household, source) -> None:
        txn(household, source, "-0.10", category(household, "Food Delivery"))
        txn(household, source, "-0.20", category(household, "Food Delivery"))

        payload = json.loads(client.get("/api/insights/spend_by_category/?month=2024-04").content)

        assert isinstance(payload["total"], str)
        assert Decimal(payload["total"]) == Decimal("0.30")

    def test_requires_authentication(self) -> None:
        assert APIClient().get("/api/insights/spend_by_category/").status_code == 403


class TestHouseholdIsolation:
    def test_another_households_spend_is_never_counted(self, client, household, source) -> None:
        stranger = User.objects.create_user(
            email="rahul@example.com", password="corr3ct-h0rse-b4ttery"
        ).default_household
        stranger_source = Source.objects.create(
            household=stranger, name="Theirs", kind=Source.Kind.BANK
        )
        txn(stranger, stranger_source, "-5000.00", category(stranger, "Food Delivery"))

        response = client.get("/api/insights/spend_by_category/?month=2024-04")

        assert response.data["total"] == "0.00"
        assert response.data["categories"] == []


class TestChartAndBudgetAgree:
    """The spend chart and the budget screen must never disagree.

    They used to: the chart counted debits only while budgets netted refunds
    off, so the same month showed two different figures for the same category.
    Both now read `transactions.services.month_spend_by_category`, and this
    test exists to keep it that way.
    """

    def test_the_same_month_reports_the_same_spend(self, household, source) -> None:
        from decimal import Decimal as D

        from apps.budgets.models import Budget
        from apps.budgets.services import budget_progress

        food = category(household, "Food & Dining")
        delivery = category(household, "Food Delivery")
        Budget.objects.create(household=household, category=food, month=APRIL, amount=D("10000.00"))
        txn(household, source, "-450.00", delivery)
        txn(household, source, "-2000.00", category(household, "Groceries"))
        txn(household, source, "150.00", delivery)  # a refund

        [budget_row] = budget_progress(household, APRIL)
        chart_row = next(
            r for r in spend_by_category(household, APRIL) if r.name == "Food & Dining"
        )

        assert budget_row.spent == chart_row.amount == D("2300.00")
