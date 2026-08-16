from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimestampedModel


class UserManager(BaseUserManager):
    """Email-as-username manager.

    Every user gets a household on creation. A user without one would be unable
    to own any financial data, so there is no code path that leaves it unset.
    """

    use_in_migrations = True

    @transaction.atomic
    def _create_user(self, email: str, password: str | None, **extra) -> "User":
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)

        household = Household.objects.create(name=extra.get("display_name") or "My household")
        HouseholdMembership.objects.create(
            user=user,
            household=household,
            role=HouseholdMembership.Role.OWNER,
        )
        return user

    def create_user(self, email: str, password: str | None = None, **extra) -> "User":
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra) -> "User":
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if extra.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin, TimestampedModel):
    """A person with a login.

    Identified by email — self-hosted instances have no use for a separate
    username, and it is one less thing for a new user to invent.
    """

    email = models.EmailField(_("email address"), unique=True)
    display_name = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")

    def __str__(self) -> str:
        return self.email

    @property
    def default_household(self) -> "Household":
        """The household new data is filed under.

        Multi-household support exists in the schema but there is no UI for
        switching yet, so this returns the oldest membership.
        """
        membership = self.memberships.order_by("created_at").first()
        if membership is None:
            raise Household.DoesNotExist(f"User {self.pk} has no household membership")
        return membership.household


class Household(TimestampedModel):
    """The tenancy boundary — one person, a couple, or a family.

    All financial data hangs off a household rather than a user so that shared
    finances work without duplicating records, and so a single deployment can
    serve several unrelated people safely.
    """

    name = models.CharField(max_length=150)
    currency = models.CharField(max_length=3, default="INR")

    def __str__(self) -> str:
        return self.name


class HouseholdMembership(TimestampedModel):
    """Links a user to a household, with a role."""

    class Role(models.TextChoices):
        OWNER = "owner", _("Owner")
        MEMBER = "member", _("Member")

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.MEMBER)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "household"], name="unique_user_household"),
        ]

    def __str__(self) -> str:
        return f"{self.user.email} @ {self.household.name} ({self.role})"
