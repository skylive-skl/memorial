from rest_framework import serializers

from apps.themes.models import Theme, ThemeAsset
from apps.themes.schema import validate_asset_refs, validate_tokens


class ThemeAssetSerializer(serializers.ModelSerializer):
    url = serializers.FileField(source="file", read_only=True)

    class Meta:
        model = ThemeAsset
        fields = ("key", "kind", "url")


class ThemeSerializer(serializers.ModelSerializer):
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

    def validate_tokens(self, value):
        errors = validate_tokens(value)
        if not errors:
            # У новой темы ещё нет ассетов: любая ссылка на ассет — ошибка.
            assets = self.instance.asset_kinds() if self.instance is not None else {}
            errors = validate_asset_refs(value, assets)
        if errors:
            raise serializers.ValidationError(errors)
        return value
