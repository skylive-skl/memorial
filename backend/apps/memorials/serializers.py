from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.memorials.models import Memorial
from apps.themes.models import Theme


class MemorialSerializer(serializers.ModelSerializer):
    theme = serializers.SlugRelatedField(
        slug_field="key",
        queryset=Theme.objects.filter(is_active=True),
        required=False,
        help_text="Ключ активной темы. При создании без темы — первая активная по sort_order.",
    )

    class Meta:
        model = Memorial
        fields = (
            "id",
            "first_name",
            "last_name",
            "middle_name",
            "birth_date",
            "birth_date_precision",
            "death_date",
            "death_date_precision",
            "description",
            "language",
            "theme",
            "theme_overrides",
            "short_code",
            "status",
            "published_at",
            "created_at",
            "updated_at",
        )
        # short_code неизменяем; статус меняется только через publish/unpublish;
        # theme_overrides в MVP не редактируется.
        read_only_fields = (
            "short_code",
            "status",
            "published_at",
            "theme_overrides",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs: dict) -> dict:
        # Даты проверяем моделью на итоговом состоянии (с учётом partial update).
        probe = Memorial(
            **{
                field: attrs.get(field, getattr(self.instance, field, None))
                for field in (
                    "birth_date",
                    "birth_date_precision",
                    "death_date",
                    "death_date_precision",
                )
            }
        )
        for field in ("birth_date_precision", "death_date_precision"):
            if getattr(probe, field) is None:
                setattr(probe, field, Memorial._meta.get_field(field).default)
        try:
            probe.validate_dates()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc
        return attrs

    def create(self, validated_data: dict) -> Memorial:
        owner = validated_data["owner"]
        validated_data.setdefault("language", owner.preferred_language)
        if "theme" not in validated_data:
            theme = Theme.objects.filter(is_active=True).order_by("sort_order", "id").first()
            if theme is None:
                raise serializers.ValidationError({"theme": "No active themes available."})
            validated_data["theme"] = theme
        return super().create(validated_data)
