from __future__ import annotations

from django.db.models import Count, Max, Min
from rest_framework import serializers

from apps.common.views import HouseholdScopedViewSet
from apps.sources.models import Source


class SourceSerializer(serializers.ModelSerializer):
    transaction_count = serializers.IntegerField(read_only=True)
    first_transaction = serializers.DateField(read_only=True)
    last_transaction = serializers.DateField(read_only=True)

    class Meta:
        model = Source
        fields = [
            "id",
            "name",
            "kind",
            "bank_slug",
            "account_hint",
            "currency",
            "is_archived",
            "transaction_count",
            "first_transaction",
            "last_transaction",
        ]
        # Sources are created by importing a statement, not by hand. The only
        # things a user should change are the label and whether it is archived
        # — the rest identifies which account statements attach to.
        read_only_fields = ["kind", "bank_slug", "account_hint"]


class SourceViewSet(HouseholdScopedViewSet):
    """Accounts and cards, created automatically when statements are imported."""

    serializer_class = SourceSerializer
    queryset = Source.objects.order_by("name")
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .annotate(
                transaction_count=Count("transactions", distinct=True),
                first_transaction=Min("transactions__txn_date"),
                last_transaction=Max("transactions__txn_date"),
            )
        )
