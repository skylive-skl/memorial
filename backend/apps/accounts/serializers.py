from typing import ClassVar

from django.contrib.auth import password_validation
from rest_framework import serializers

from apps.accounts.models import User, normalize_email


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "preferred_language", "created_at")
        read_only_fields = fields


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta:
        model = User
        fields = ("email", "password", "preferred_language")
        # Уникальность проверяем сами — без учёта регистра.
        extra_kwargs: ClassVar[dict] = {"email": {"validators": []}}

    def validate_email(self, value: str) -> str:
        email = normalize_email(value)
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError(
                "A user with this email already exists.", code="email_taken"
            )
        return email

    def validate(self, attrs: dict) -> dict:
        password_validation.validate_password(attrs["password"], User(email=attrs["email"]))
        return attrs

    def create(self, validated_data: dict) -> User:
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
