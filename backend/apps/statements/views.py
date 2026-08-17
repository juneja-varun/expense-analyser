from __future__ import annotations

from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from apps.common.views import HouseholdScopedViewSet
from apps.parsers.registry import supported_banks
from apps.statements.models import Statement
from apps.statements.services import import_statement

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_EXTENSIONS = {"pdf", "csv", "xls", "xlsx", "txt"}


class StatementSerializer(serializers.ModelSerializer):
    source_name = serializers.CharField(source="source.name", read_only=True)
    was_entirely_duplicate = serializers.BooleanField(read_only=True)

    class Meta:
        model = Statement
        fields = [
            "id",
            "original_filename",
            "status",
            "bank_slug",
            "statement_kind",
            "source",
            "source_name",
            "period_start",
            "period_end",
            "transaction_count",
            "duplicate_count",
            "error_message",
            "was_entirely_duplicate",
            "created_at",
        ]
        read_only_fields = fields


class StatementUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    password = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="For password-protected PDFs. Used to open the file; never stored.",
    )
    bank_slug = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Set only when automatic detection picked the wrong bank.",
    )

    def validate_file(self, uploaded):
        if uploaded.size > MAX_UPLOAD_BYTES:
            raise serializers.ValidationError(
                f"That file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB. "
                "Statements are normally well under a megabyte — is this the right file?"
            )

        extension = uploaded.name.rsplit(".", 1)[-1].lower() if "." in uploaded.name else ""
        if extension not in ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                f"{extension or 'That file type'} isn't supported. Upload the PDF, CSV or "
                "XLS your bank provides."
            )
        return uploaded


class StatementViewSet(HouseholdScopedViewSet):
    """Uploaded statements and the outcome of importing them."""

    serializer_class = StatementSerializer
    queryset = Statement.objects.select_related("source").order_by("-created_at")
    parser_classes = [MultiPartParser, FormParser]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def create(self, request: Request, *args, **kwargs) -> Response:
        """Upload a statement and import it.

        Imports synchronously: a statement is a few hundred rows and parses in
        well under a second, so a background worker would add a dependency and
        a progress-polling UI for no real gain. If large statements ever make
        this slow, this is the single place to move it off the request.

        A file we cannot parse is **not** an error response — the upload
        succeeded, and `status: failed` with `error_message` is the useful
        outcome for the UI to render.
        """
        upload = StatementUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)

        uploaded = upload.validated_data["file"]
        statement = Statement(
            household=request.user.default_household,
            original_filename=uploaded.name,
        )
        statement.file = uploaded
        statement.save()

        result = import_statement(
            statement,
            password=upload.validated_data.get("password") or None,
            bank_slug=upload.validated_data.get("bank_slug") or None,
        )

        return Response(
            {
                **StatementSerializer(result.statement).data,
                "created": result.created,
                "duplicates": result.duplicates,
            },
            status=status.HTTP_201_CREATED,
        )

    def perform_destroy(self, instance: Statement) -> None:
        """Deleting an upload removes the file, never the transactions.

        `Transaction.statement` is SET_NULL — a user tidying their upload
        history must not lose their financial records.
        """
        instance.file.delete(save=False)
        instance.delete()

    @action(detail=False, methods=["get"])
    def supported_banks(self, request: Request) -> Response:
        """Which banks can be parsed — drives the upload screen's guidance."""
        return Response(supported_banks())
