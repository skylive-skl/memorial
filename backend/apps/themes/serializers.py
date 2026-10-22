from django.conf import settings
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.themes.models import Theme, ThemeAsset
from apps.themes.schema import validate_asset_refs, validate_tokens


class ThemeAssetSerializer(serializers.ModelSerializer):
    url = serializers.FileField(source="file", read_only=True)

    class Meta:
        model = ThemeAsset
        fields = ("key", "kind", "url")


class ThemeSerializer(serializers.ModelSerializer):
    # Все переводы сразу: язык выбирает фронт. Пустой перевод — русский.
    name = serializers.SerializerMethodField()
    assets = ThemeAssetSerializer(many=True, read_only=True)

    class Meta:
        model = Theme
        fields = (
            "key",
            "name",
            "category",
            "layout_key",
            "tokens",
            "preview_image",
            "version",
            "assets",
        )
        read_only_fields = ("layout_key", "version", "assets")

    @extend_schema_field(
        {
            "type": "object",
            "properties": {code: {"type": "string"} for code, _ in settings.LANGUAGES},
            "required": [code for code, _ in settings.LANGUAGES],
        }
    )
    def get_name(self, theme: Theme) -> dict[str, str]:
        return {
            code: getattr(theme, f"name_{code}") or theme.name_ru for code, _ in settings.LANGUAGES
        }

    def validate_tokens(self, value):
        errors = validate_tokens(value)
        if not errors:
            # У новой темы ещё нет ассетов: любая ссылка на ассет — ошибка.
            assets = self.instance.asset_kinds() if self.instance is not None else {}
            errors = validate_asset_refs(value, assets)
        if errors:
            raise serializers.ValidationError(errors)
        return value
