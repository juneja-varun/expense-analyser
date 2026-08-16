from django.contrib.auth import authenticate, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.accounts.models import Household, User


class HouseholdSerializer(serializers.ModelSerializer):
    class Meta:
        model = Household
        fields = ["id", "name", "currency"]


class UserSerializer(serializers.ModelSerializer):
    household = HouseholdSerializer(source="default_household", read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "display_name", "household", "date_joined"]
        read_only_fields = fields


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ["email", "display_name", "password"]

    def validate_email(self, value: str) -> str:
        normalised = value.lower().strip()
        if User.objects.filter(email=normalised).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return normalised

    def validate_password(self, value: str) -> str:
        try:
            password_validation.validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value

    def create(self, validated_data: dict) -> User:
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, attrs: dict) -> dict:
        user = authenticate(
            request=self.context.get("request"),
            username=attrs["email"].lower().strip(),
            password=attrs["password"],
        )
        # Deliberately identical message for unknown email and wrong password,
        # so the endpoint cannot be used to enumerate registered addresses.
        if user is None:
            raise serializers.ValidationError("Incorrect email or password.")
        if not user.is_active:
            raise serializers.ValidationError("This account is inactive.")
        attrs["user"] = user
        return attrs
