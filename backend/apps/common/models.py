from django.db import models


class TimestampedModel(models.Model):
    """Adds created/updated bookkeeping to any model."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class HouseholdScopedQuerySet(models.QuerySet):
    """QuerySet for data owned by exactly one household."""

    def for_household(self, household) -> "HouseholdScopedQuerySet":
        return self.filter(household=household)

    def for_user(self, user) -> "HouseholdScopedQuerySet":
        """Every household the user belongs to.

        Users normally have one household, but the data model allows several
        (personal + shared, say), so this returns the union rather than
        assuming a single membership.
        """
        if not user.is_authenticated:
            return self.none()
        return self.filter(household__memberships__user=user).distinct()


class HouseholdScopedModel(TimestampedModel):
    """Base class for every model holding user financial data.

    The `household` FK is the tenancy boundary. Two safeguards sit on top of it:

    * `objects.for_household()` / `for_user()` make scoping a one-call operation.
    * `HouseholdScopedViewSet` (apps/common/views.py) refuses to serve a
      queryset that has not been scoped, so forgetting the filter fails loudly
      in development instead of silently leaking another household's data.

    Anything financial inherits from this. If you are adding a model and
    wondering whether it needs a household, the answer is almost certainly yes.
    """

    household = models.ForeignKey(
        "accounts.Household",
        on_delete=models.CASCADE,
        related_name="%(class)ss",
        db_index=True,
    )

    objects = HouseholdScopedQuerySet.as_manager()

    class Meta:
        abstract = True
