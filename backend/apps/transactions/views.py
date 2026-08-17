from __future__ import annotations

from decimal import Decimal

from django.db.models import Q, QuerySet, Sum
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.request import Request
from rest_framework.response import Response

from apps.common.views import HouseholdScopedViewSet
from apps.rules.engine import categorise_transactions, learn_from_recategorisation
from apps.transactions.models import Transaction
from apps.transactions.serializers import TransactionSerializer


def category_subtree(category_id: str) -> Q:
    """Match a category or anything nested beneath it.

    Filtering by a parent should include the spend sitting on its children —
    picking "Food & Dining" and seeing nothing would be surprising. The tree is
    at most three levels deep, so this needs no recursion.
    """
    return (
        Q(category_id=category_id)
        | Q(category__parent_id=category_id)
        | Q(category__parent__parent_id=category_id)
    )


class TransactionViewSet(HouseholdScopedViewSet):
    """The household's transactions.

    Read-mostly: what the bank said is immutable, and only the category and the
    user's own notes can change.
    """

    serializer_class = TransactionSerializer
    queryset = Transaction.objects.select_related("category", "source").order_by("-txn_date", "-id")
    # POST is allowed for the custom actions below, not for creating
    # transactions — those only ever come from importing a statement, so
    # `create` is disabled explicitly.
    http_method_names = ["get", "post", "patch", "head", "options"]

    def create(self, request: Request, *args, **kwargs):
        raise MethodNotAllowed(
            request.method,
            detail="Transactions are created by uploading a statement, not directly.",
        )

    def get_queryset(self) -> QuerySet[Transaction]:
        queryset = super().get_queryset()
        params = self.request.query_params

        if start := params.get("start_date"):
            queryset = queryset.filter(txn_date__gte=start)
        if end := params.get("end_date"):
            queryset = queryset.filter(txn_date__lte=end)
        if source := params.get("source"):
            queryset = queryset.filter(source_id=source)
        if search := params.get("search"):
            queryset = queryset.filter(description__icontains=search)

        category = params.get("category")
        if category == "none":
            queryset = queryset.filter(category__isnull=True)
        elif category:
            queryset = queryset.filter(category_subtree(category))

        direction = params.get("direction")
        if direction == "debit":
            queryset = queryset.filter(amount__lt=0)
        elif direction == "credit":
            queryset = queryset.filter(amount__gt=0)

        return queryset

    def perform_update(self, serializer) -> None:
        """Recategorising is the moment the app learns.

        Choosing a category by hand marks the transaction so no future import
        can silently overwrite it, and turns the correction into a rule so the
        same merchant never has to be classified twice.
        """
        previous_category_id = serializer.instance.category_id
        updated = serializer.save()

        if "category" not in serializer.validated_data:
            return
        if updated.category_id == previous_category_id:
            return

        if updated.category_id is None:
            # Clearing a category is a correction too, but there is nothing to
            # learn from "this is not anything".
            updated.is_categorised_by_user = False
            updated.save(update_fields=["is_categorised_by_user", "updated_at"])
            return

        updated.is_categorised_by_user = True
        updated.save(update_fields=["is_categorised_by_user", "updated_at"])
        learn_from_recategorisation(updated, updated.category)

    @action(detail=False, methods=["post"])
    def recategorise(self, request: Request) -> Response:
        """Re-run the rules over this household's transactions.

        Manual choices are preserved unless `include_user_categorised` is sent
        — the "I've rewritten my rules, redo everything" case.
        """
        result = categorise_transactions(
            request.user.default_household,
            include_user_categorised=bool(request.data.get("include_user_categorised")),
        )
        return Response(
            {
                "categorised": result.categorised,
                "unmatched": result.unmatched,
                "skipped_user_categorised": result.skipped_user_categorised,
            }
        )

    @action(detail=False, methods=["get"])
    def summary(self, request: Request) -> Response:
        """Totals for the current filter — what a list view shows in its header."""
        queryset = self.get_queryset()
        totals = queryset.aggregate(
            spent=Sum("amount", filter=Q(amount__lt=0)),
            received=Sum("amount", filter=Q(amount__gt=0)),
        )
        spent = totals["spent"] or Decimal("0")
        received = totals["received"] or Decimal("0")

        return Response(
            {
                "count": queryset.count(),
                "spent": abs(spent),
                "received": received,
                "net": received + spent,
                "uncategorised": queryset.filter(category__isnull=True).count(),
            }
        )
