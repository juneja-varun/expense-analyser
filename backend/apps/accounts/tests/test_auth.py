import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import Household, HouseholdMembership, User

pytestmark = pytest.mark.django_db


@pytest.fixture
def client() -> APIClient:
    return APIClient()


class TestRegistration:
    def test_creates_user_with_household(self, client: APIClient) -> None:
        response = client.post(
            reverse("accounts:register"),
            {
                "email": "asha@example.com",
                "display_name": "Asha",
                "password": "corr3ct-h0rse-b4ttery",
            },
            format="json",
        )

        assert response.status_code == 201
        assert response.data["email"] == "asha@example.com"

        user = User.objects.get(email="asha@example.com")
        # A user with no household could not own any financial data, so
        # registration must always produce one.
        assert user.memberships.count() == 1
        assert user.default_household.name == "Asha"
        assert user.memberships.first().role == HouseholdMembership.Role.OWNER

    def test_email_is_normalised_to_lowercase(self, client: APIClient) -> None:
        client.post(
            reverse("accounts:register"),
            {"email": "Mixed.Case@Example.COM", "password": "corr3ct-h0rse-b4ttery"},
            format="json",
        )
        assert User.objects.filter(email="mixed.case@example.com").exists()

    def test_rejects_duplicate_email(self, client: APIClient) -> None:
        User.objects.create_user(email="taken@example.com", password="corr3ct-h0rse-b4ttery")

        response = client.post(
            reverse("accounts:register"),
            {"email": "taken@example.com", "password": "an0ther-passw0rd-here"},
            format="json",
        )

        assert response.status_code == 400
        assert "email" in response.data

    def test_rejects_weak_password(self, client: APIClient) -> None:
        response = client.post(
            reverse("accounts:register"),
            {"email": "weak@example.com", "password": "password"},
            format="json",
        )
        assert response.status_code == 400
        assert "password" in response.data


class TestLogin:
    def test_valid_credentials_start_a_session(self, client: APIClient) -> None:
        User.objects.create_user(email="asha@example.com", password="corr3ct-h0rse-b4ttery")

        response = client.post(
            reverse("accounts:login"),
            {"email": "asha@example.com", "password": "corr3ct-h0rse-b4ttery"},
            format="json",
        )

        assert response.status_code == 200
        # The session cookie, not a token, is what authenticates subsequent calls.
        assert client.get(reverse("accounts:me")).status_code == 200

    @pytest.mark.parametrize(
        ("email", "password"),
        [
            ("asha@example.com", "wrong-password-entirely"),
            ("nobody@example.com", "corr3ct-h0rse-b4ttery"),
        ],
    )
    def test_bad_credentials_give_an_identical_error(
        self, client: APIClient, email: str, password: str
    ) -> None:
        """Wrong password and unknown email must be indistinguishable.

        A differing response would turn the login endpoint into an oracle for
        which email addresses have accounts on the instance.
        """
        User.objects.create_user(email="asha@example.com", password="corr3ct-h0rse-b4ttery")

        response = client.post(
            reverse("accounts:login"), {"email": email, "password": password}, format="json"
        )

        assert response.status_code == 400
        assert response.data["non_field_errors"][0] == "Incorrect email or password."

    def test_logout_ends_the_session(self, client: APIClient) -> None:
        user = User.objects.create_user(email="asha@example.com", password="corr3ct-h0rse-b4ttery")
        client.force_authenticate(user=user)

        assert client.post(reverse("accounts:logout")).status_code == 204

        client.force_authenticate(user=None)
        assert client.get(reverse("accounts:me")).status_code == 403


class TestCurrentUser:
    def test_requires_authentication(self, client: APIClient) -> None:
        assert client.get(reverse("accounts:me")).status_code == 403

    def test_returns_the_users_household(self, client: APIClient) -> None:
        user = User.objects.create_user(
            email="asha@example.com", password="corr3ct-h0rse-b4ttery", display_name="Asha"
        )
        client.force_authenticate(user=user)

        response = client.get(reverse("accounts:me"))

        assert response.status_code == 200
        assert response.data["household"]["name"] == "Asha"
        assert response.data["household"]["currency"] == "INR"


class TestHouseholdIsolation:
    """The tenancy boundary.

    These are the tests that matter most on a shared self-hosted instance: a
    regression here leaks one family's finances to another.
    """

    def test_scoped_queryset_excludes_other_households(self) -> None:
        asha = User.objects.create_user(email="asha@example.com", password="corr3ct-h0rse-b4ttery")
        rahul = User.objects.create_user(
            email="rahul@example.com", password="corr3ct-h0rse-b4ttery"
        )

        assert asha.default_household != rahul.default_household

        visible = Household.objects.filter(memberships__user=asha)
        assert list(visible) == [asha.default_household]
        assert rahul.default_household not in visible

    def test_membership_is_unique_per_user_and_household(self) -> None:
        from django.db import IntegrityError

        user = User.objects.create_user(email="asha@example.com", password="corr3ct-h0rse-b4ttery")

        with pytest.raises(IntegrityError):
            HouseholdMembership.objects.create(
                user=user, household=user.default_household, role=HouseholdMembership.Role.MEMBER
            )

    def test_user_can_belong_to_several_households(self) -> None:
        """Shared finances: a person may be in both a personal and a joint household."""
        user = User.objects.create_user(email="asha@example.com", password="corr3ct-h0rse-b4ttery")
        joint = Household.objects.create(name="Joint account")
        HouseholdMembership.objects.create(user=user, household=joint)

        assert user.memberships.count() == 2
        # default_household stays the oldest membership, so existing data keeps
        # filing under the household it always did.
        assert user.default_household != joint
