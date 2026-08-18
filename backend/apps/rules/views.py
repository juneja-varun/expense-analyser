from __future__ import annotations

import re

from django.db.models import QuerySet
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.common.views import HouseholdScopedViewSet
from apps.rules.engine import categorise_transactions, distinctive_fragment
from apps.rules.models import (
    CategoryRule,
    extract_vpa,
    matchable_text,
    normalise_for_matching,
)
from apps.rules.serializers import CategoryRuleSerializer
from apps.transactions.models import Transaction

# Enough to show the user what a rule catches without turning a preview into a
# page-load. If a pattern matches more than this, the count is what matters.
PREVIEW_LIMIT = 5


def suggest_rule(description: str) -> tuple[str, str]:
    """The rule that best identifies a merchant from one narration.

    Mirrors what `learn_from_recategorisation` does automatically, so the rule a
    user is shown is the rule the app would have written itself. Where that
    function gives up and returns None, this one falls back to matching the whole
    description exactly — for a rule the user is explicitly reviewing, "too
    narrow" is a fine default, whereas silently learning a narrow rule would not
    have been worth the row in the database.
    """
    vpa = extract_vpa(description)
    if vpa:
        return CategoryRule.MatchType.UPI_VPA, vpa

    fragment = distinctive_fragment(description)
    if fragment:
        return CategoryRule.MatchType.CONTAINS, fragment

    # Matched against the same stripped text `matches()` uses, or an EXACT rule
    # suggested here would never fire.
    return CategoryRule.MatchType.EXACT, normalise_for_matching(matchable_text(description))


class CategoryRuleViewSet(HouseholdScopedViewSet):
    """The household's categorisation rules.

    Rules the app learned and rules shipped with it are listed alongside the
    user's own so they can be corrected or switched off — a wrong rule the user
    cannot see is worse than no rule.
    """

    serializer_class = CategoryRuleSerializer
    queryset = CategoryRule.objects.select_related("category").order_by("-priority", "id")

    def get_queryset(self) -> QuerySet[CategoryRule]:
        queryset = super().get_queryset()
        params = self.request.query_params

        if origin := params.get("origin"):
            queryset = queryset.filter(origin=origin)
        if (active := params.get("is_active")) is not None:
            queryset = queryset.filter(is_active=active.lower() not in {"false", "0"})
        if category := params.get("category"):
            queryset = queryset.filter(category_id=category)

        return queryset

    def create(self, request: Request, *args, **kwargs) -> Response:
        """Create a rule and immediately apply it.

        A rule that does not visibly do anything until the next import reads as
        broken. Applying on save means the transaction the user was looking at
        when they wrote the rule is categorised by the time the response lands.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        result = categorise_transactions(request.user.default_household)
        data = {**serializer.data, "applied": result.categorised}
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def suggest(self, request: Request) -> Response:
        """What rule would catch this description, and what else it would catch.

        The preview is the point. `CONTAINS "CHAI"` looks harmless until you see
        it also matches a chemist called Chaitanya, and that is far cheaper to
        discover here than after it has recategorised a year of history.

        Pass `description` for a suggested rule, or `pattern` (with an optional
        `match_type`) to preview one the user has edited — the same endpoint
        answers both so the preview cannot disagree with the suggestion.
        """
        description = request.query_params.get("description", "").strip()
        override = request.query_params.get("pattern", "").strip()
        if not description and not override:
            return Response(
                {"detail": "Pass a `description` to get a suggestion, or a `pattern` to preview."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if override:
            match_type = request.query_params.get("match_type") or CategoryRule.MatchType.CONTAINS
            if match_type not in CategoryRule.MatchType.values:
                return Response(
                    {"match_type": f"Not one of {', '.join(CategoryRule.MatchType.values)}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            pattern = override
        else:
            match_type, pattern = suggest_rule(description)

        candidate = CategoryRule(match_type=match_type, pattern=pattern)
        if match_type == CategoryRule.MatchType.REGEX:
            # `matches()` swallows a bad regex so one broken rule cannot stop
            # the engine. Here that would render as a silent "0 matches", which
            # reads as a working rule that catches nothing.
            try:
                re.compile(pattern)
            except re.error as exc:
                return Response(
                    {"pattern": f"Not a valid regular expression: {exc}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Matching runs in Python because `matches()` is the single definition
        # of what a rule does — reimplementing it as an ORM lookup here would
        # let the preview and the engine drift apart, and a preview that lies
        # is worse than none.
        household = request.user.default_household
        rows = (
            Transaction.objects.for_household(household)
            .select_related("category")
            .order_by("-txn_date", "-id")
        )
        matched = [row for row in rows if candidate.matches(row.description)]

        # A rule does not overrule a person. `categorise_transactions` leaves
        # hand-filed transactions alone, so counting them among the rows this
        # rule "will recategorise" would promise something that then quietly
        # does not happen.
        protected = sum(1 for row in matched if row.is_categorised_by_user)

        return Response(
            {
                "match_type": match_type,
                "match_type_label": CategoryRule.MatchType(match_type).label,
                "pattern": pattern,
                "matches": len(matched),
                "protected": protected,
                "examples": [
                    {
                        "id": row.id,
                        "description": row.description,
                        "txn_date": row.txn_date,
                        "category_name": row.category.full_name if row.category_id else None,
                        "is_categorised_by_user": row.is_categorised_by_user,
                    }
                    for row in matched[:PREVIEW_LIMIT]
                ],
            }
        )
