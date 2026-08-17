"""API behaviour, exercised through HTTP rather than by calling services."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.categories.models import Category
from apps.rules.models import CategoryRule
from apps.sources.models import Source
from apps.transactions.models import Transaction

pytestmark = pytest.mark.django_db

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "apps"
    / "parsers"
    / "banks"
    / "hdfc"
    / "tests"
    / "fixtures"
    / "hdfc_savings_2024_04.xls"
)


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def user():
    return User.objects.create_user(email="asha@example.com", password="corr3ct-h0rse-b4ttery")


@pytest.fixture
def client(user) -> APIClient:
    api = APIClient()
    api.force_authenticate(user=user)
    return api


@pytest.fixture
def household(user):
    return user.default_household


@pytest.fixture
def source(household):
    return Source.objects.create(household=household, name="HDFC", kind=Source.Kind.BANK)


def category(household, name: str) -> Category:
    return Category.objects.for_household(household).get(name=name)


def make_transaction(household, source, description="UPI-SWIGGY-PAY", amount="-450.00", **kwargs):
    return Transaction.objects.create(
        household=household,
        source=source,
        txn_date=kwargs.pop("txn_date", date(2024, 4, 3)),
        description=description,
        amount=Decimal(amount),
        **kwargs,
    )


class TestAuthentication:
    @pytest.mark.parametrize(
        "url",
        ["/api/transactions/", "/api/categories/", "/api/statements/", "/api/sources/"],
    )
    def test_endpoints_require_a_session(self, url: str) -> None:
        assert APIClient().get(url).status_code == 403


class TestTransactions:
    def test_lists_the_households_transactions(self, client, household, source) -> None:
        make_transaction(household, source)

        response = client.get("/api/transactions/")

        assert response.status_code == 200
        assert response.data["count"] == 1
        assert response.data["results"][0]["description"] == "UPI-SWIGGY-PAY"

    def test_statement_fields_are_read_only(self, client, household, source) -> None:
        """A transaction records what the bank said; only the category and the
        user's own notes may change."""
        txn = make_transaction(household, source)

        response = client.patch(
            f"/api/transactions/{txn.pk}/",
            {"amount": "-1.00", "description": "edited"},
            format="json",
        )

        txn.refresh_from_db()
        assert response.status_code == 200
        assert txn.amount == Decimal("-450.00")
        assert txn.description == "UPI-SWIGGY-PAY"

    def test_notes_can_be_edited(self, client, household, source) -> None:
        txn = make_transaction(household, source)

        client.patch(f"/api/transactions/{txn.pk}/", {"notes": "split with Rahul"}, format="json")

        txn.refresh_from_db()
        assert txn.notes == "split with Rahul"

    @pytest.mark.parametrize(
        ("params", "expected"),
        [
            ("?direction=debit", 1),
            ("?direction=credit", 1),
            ("?search=swiggy", 1),
            ("?search=nothing-matches", 0),
            ("?category=none", 2),
            ("?start_date=2024-05-01", 1),
            ("?end_date=2024-04-30", 1),
        ],
    )
    def test_filtering(self, client, household, source, params: str, expected: int) -> None:
        make_transaction(household, source, "UPI-SWIGGY-PAY", "-450.00")
        make_transaction(household, source, "SALARY CREDIT", "125000.00", txn_date=date(2024, 5, 1))

        response = client.get(f"/api/transactions/{params}")

        assert response.data["count"] == expected

    def test_filtering_by_a_parent_category_includes_its_children(
        self, client, household, source
    ) -> None:
        """Picking "Food & Dining" and seeing nothing, because the spend sits on
        a child category, would be surprising."""
        food = category(household, "Food & Dining")
        delivery = category(household, "Food Delivery")
        make_transaction(household, source, category=delivery)

        response = client.get(f"/api/transactions/?category={food.pk}")

        assert response.data["count"] == 1

    def test_summary_totals(self, client, household, source) -> None:
        make_transaction(household, source, "UPI-SWIGGY-PAY", "-450.00")
        make_transaction(household, source, "SALARY", "125000.00")

        response = client.get("/api/transactions/summary/")

        assert response.data["count"] == 2
        assert Decimal(response.data["spent"]) == Decimal("450.00")
        assert Decimal(response.data["received"]) == Decimal("125000.00")
        assert Decimal(response.data["net"]) == Decimal("124550.00")
        assert response.data["uncategorised"] == 2


class TestRecategorising:
    def test_setting_a_category_marks_it_as_the_users_choice(
        self, client, household, source
    ) -> None:
        txn = make_transaction(household, source)
        delivery = category(household, "Food Delivery")

        response = client.patch(
            f"/api/transactions/{txn.pk}/", {"category": delivery.pk}, format="json"
        )

        txn.refresh_from_db()
        assert response.status_code == 200
        assert txn.category == delivery
        assert txn.is_categorised_by_user is True

    def test_recategorising_teaches_the_rules_engine(self, client, household, source) -> None:
        """The correction becomes a rule, so the same merchant is never
        classified by hand twice."""
        txn = make_transaction(household, source, "UPI-SWIGGY-SWIGGY@EXAMPLEBANK-PAY")
        delivery = category(household, "Food Delivery")

        client.patch(f"/api/transactions/{txn.pk}/", {"category": delivery.pk}, format="json")

        rule = CategoryRule.objects.for_household(household).get(origin=CategoryRule.Origin.LEARNED)
        assert rule.pattern == "swiggy@examplebank"
        assert rule.category == delivery
        assert rule.origin == CategoryRule.Origin.LEARNED

    def test_clearing_a_category_learns_nothing(self, client, household, source) -> None:
        """There is nothing to learn from "this is not anything"."""
        delivery = category(household, "Food Delivery")
        txn = make_transaction(household, source, category=delivery)

        client.patch(f"/api/transactions/{txn.pk}/", {"category": None}, format="json")

        txn.refresh_from_db()
        assert txn.category is None
        assert txn.is_categorised_by_user is False
        learned = CategoryRule.objects.for_household(household).filter(
            origin=CategoryRule.Origin.LEARNED
        )
        assert not learned.exists()

    def test_cannot_use_another_households_category(self, client, household, source) -> None:
        stranger = User.objects.create_user(
            email="rahul@example.com", password="corr3ct-h0rse-b4ttery"
        ).default_household
        theirs = category(stranger, "Food Delivery")
        txn = make_transaction(household, source)

        response = client.patch(
            f"/api/transactions/{txn.pk}/", {"category": theirs.pk}, format="json"
        )

        assert response.status_code == 400

    def test_bulk_recategorise_endpoint(self, client, household, source) -> None:
        # SWIGGY is already a bundled rule, so no rule is created here — the
        # point is that the endpoint applies whatever rules the household has.
        make_transaction(household, source, "UPI-SWIGGY-PAY")

        response = client.post("/api/transactions/recategorise/", {}, format="json")

        assert response.status_code == 200
        assert response.data["categorised"] == 1


class TestCategories:
    def test_lists_the_seeded_tree(self, client) -> None:
        response = client.get("/api/categories/?limit=200")

        assert response.status_code == 200
        assert response.data["count"] > 40

    def test_tree_endpoint_nests_children(self, client) -> None:
        response = client.get("/api/categories/tree/")

        food = next(c for c in response.data if c["name"] == "Food & Dining")
        eating_out = next(c for c in food["children"] if c["name"] == "Eating Out")
        assert any(c["name"] == "Food Delivery" for c in eating_out["children"])

    def test_can_create_a_child_category(self, client, household) -> None:
        parent = category(household, "Eating Out")

        response = client.post(
            "/api/categories/", {"name": "Weekend", "parent": parent.pk}, format="json"
        )

        assert response.status_code == 201
        assert response.data["depth"] == 2
        assert response.data["full_name"] == "Food & Dining → Eating Out → Weekend"

    def test_rejects_a_fourth_level(self, client, household) -> None:
        deepest = category(household, "Food Delivery")

        response = client.post(
            "/api/categories/", {"name": "Too deep", "parent": deepest.pk}, format="json"
        )

        assert response.status_code == 400
        assert "3 levels" in str(response.data)

    def test_built_in_categories_cannot_be_deleted(self, client, household) -> None:
        """The rest of the app assumes the default tree exists."""
        seeded = category(household, "Food & Dining")

        response = client.delete(f"/api/categories/{seeded.pk}/")

        assert response.status_code == 400
        assert Category.objects.filter(pk=seeded.pk).exists()

    def test_user_categories_can_be_deleted_without_losing_transactions(
        self, client, household, source
    ) -> None:
        created = client.post("/api/categories/", {"name": "Hobbies"}, format="json").data
        txn = make_transaction(household, source, category_id=created["id"])

        response = client.delete(f"/api/categories/{created['id']}/")

        txn.refresh_from_db()
        assert response.status_code == 204
        assert txn.category is None


class TestStatementUpload:
    def test_uploading_imports_transactions(self, client, household) -> None:
        upload = SimpleUploadedFile(FIXTURE.name, FIXTURE.read_bytes())

        response = client.post("/api/statements/", {"file": upload}, format="multipart")

        assert response.status_code == 201
        assert response.data["status"] == "parsed"
        assert response.data["created"] == 10
        assert Transaction.objects.for_household(household).count() == 10

    def test_reuploading_reports_duplicates_rather_than_doubling(self, client, household) -> None:
        for _ in range(2):
            response = client.post(
                "/api/statements/",
                {"file": SimpleUploadedFile(FIXTURE.name, FIXTURE.read_bytes())},
                format="multipart",
            )

        assert response.data["created"] == 0
        assert response.data["duplicates"] == 10
        assert response.data["was_entirely_duplicate"] is True
        assert Transaction.objects.for_household(household).count() == 10

    def test_an_unparseable_file_is_a_successful_upload_with_a_failed_status(self, client) -> None:
        """The upload worked; we just couldn't read it. A 400 would tell the UI
        the request was malformed, which is misleading."""
        upload = SimpleUploadedFile("holiday.csv", b"not a bank statement at all\n")

        response = client.post("/api/statements/", {"file": upload}, format="multipart")

        assert response.status_code == 201
        assert response.data["status"] == "failed"
        assert "no parser recognised" in response.data["error_message"].lower()

    def test_rejects_an_unsupported_file_type(self, client) -> None:
        upload = SimpleUploadedFile("cat.png", b"\x89PNG\r\n")

        response = client.post("/api/statements/", {"file": upload}, format="multipart")

        assert response.status_code == 400
        assert "supported" in str(response.data).lower()

    def test_deleting_a_statement_keeps_its_transactions(self, client, household) -> None:
        statement_id = client.post(
            "/api/statements/",
            {"file": SimpleUploadedFile(FIXTURE.name, FIXTURE.read_bytes())},
            format="multipart",
        ).data["id"]

        response = client.delete(f"/api/statements/{statement_id}/")

        assert response.status_code == 204
        assert Transaction.objects.for_household(household).count() == 10

    def test_supported_banks_endpoint(self, client) -> None:
        response = client.get("/api/statements/supported_banks/")

        slugs = {bank["bank_slug"] for bank in response.data}
        assert {"hdfc", "icici"} <= slugs


class TestHouseholdIsolation:
    """The boundary that matters most on a shared instance."""

    @pytest.fixture
    def stranger_data(self):
        stranger = User.objects.create_user(
            email="rahul@example.com", password="corr3ct-h0rse-b4ttery"
        )
        household = stranger.default_household
        source = Source.objects.create(
            household=household, name="Their bank", kind=Source.Kind.BANK
        )
        return make_transaction(household, source, "THEIR PRIVATE TRANSACTION")

    def test_list_never_returns_another_households_transactions(
        self, client, stranger_data
    ) -> None:
        response = client.get("/api/transactions/")

        assert response.data["count"] == 0

    def test_cannot_fetch_another_households_transaction_by_id(self, client, stranger_data) -> None:
        assert client.get(f"/api/transactions/{stranger_data.pk}/").status_code == 404

    def test_cannot_modify_another_households_transaction(self, client, stranger_data) -> None:
        response = client.patch(
            f"/api/transactions/{stranger_data.pk}/", {"notes": "seen"}, format="json"
        )

        stranger_data.refresh_from_db()
        assert response.status_code == 404
        assert stranger_data.notes == ""

    def test_cannot_see_another_households_categories(self, client, stranger_data) -> None:
        theirs = Category.objects.for_household(stranger_data.household).first()

        assert client.get(f"/api/categories/{theirs.pk}/").status_code == 404

    def test_cannot_see_another_households_sources(self, client, stranger_data) -> None:
        response = client.get("/api/sources/")

        assert all(s["name"] != "Their bank" for s in response.data["results"])
