from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.memorials.images import UnsupportedImage, detect_format
from apps.memorials.models import Memorial, Photo
from apps.themes.models import Theme

_variants_schema = {
    "type": "object",
    "properties": {name: {"type": "string", "format": "uri"} for name in settings.PHOTO_VARIANTS},
}


class PhotoSerializer(serializers.ModelSerializer):
    variants = serializers.SerializerMethodField()

    class Meta:
        model = Photo
        fields = (
            "id",
            "original",
            "variants",
            "caption",
            "order",
            "is_cover",
            "width",
            "height",
            "processing_status",
            "created_at",
        )
        read_only_fields = (
            "original",
            "order",
            "width",
            "height",
            "processing_status",
            "created_at",
        )

    @extend_schema_field(_variants_schema)
    def get_variants(self, photo: Photo) -> dict[str, str]:
        storage = photo.original.storage
        return {name: storage.url(key) for name, key in photo.variants.items()}


class PhotoUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    caption = serializers.CharField(max_length=500, required=False, allow_blank=True)

    def validate_file(self, file):
        if file.size > settings.PHOTO_MAX_UPLOAD_BYTES:
            limit_mb = settings.PHOTO_MAX_UPLOAD_BYTES // (1024 * 1024)
            raise serializers.ValidationError(
                f"File is too large (max {limit_mb} MB).", code="file_too_large"
            )
        try:
            detect_format(file)
        except UnsupportedImage as exc:
            raise serializers.ValidationError(str(exc), code="unsupported_image") from exc
        return file


class MemorialSerializer(serializers.ModelSerializer):
    theme = serializers.SlugRelatedField(
        slug_field="key",
        queryset=Theme.objects.filter(is_active=True),
        required=False,
        help_text="Ключ активной темы. При создании без темы — первая активная по sort_order.",
    )
    photos = PhotoSerializer(many=True, read_only=True)

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
            "photos",
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


# --- Публичная страница (/public/m/{short_code}/) ---
# Только то, что нужно для рендера: без владельца, внутренних id, оригиналов фото
# и служебных полей.


class PublicPhotoSerializer(serializers.ModelSerializer):
    variants = serializers.SerializerMethodField()

    class Meta:
        model = Photo
        fields = ("caption", "is_cover", "width", "height", "variants")

    @extend_schema_field(_variants_schema)
    def get_variants(self, photo: Photo) -> dict[str, str]:
        storage = photo.original.storage
        return {name: storage.url(key) for name, key in photo.variants.items()}


class ResolvedThemeSerializer(serializers.ModelSerializer):
    """Тема для рендера: tokens как есть + абсолютные URL ассетов по ключам из tokens."""

    assets = serializers.SerializerMethodField()

    class Meta:
        model = Theme
        fields = ("key", "version", "tokens", "assets")

    @extend_schema_field(
        {"type": "object", "additionalProperties": {"type": "string", "format": "uri"}}
    )
    def get_assets(self, theme: Theme) -> dict[str, str]:
        return {asset.key: asset.file.url for asset in theme.assets.all()}


class PublicMemorialSerializer(serializers.ModelSerializer):
    theme = ResolvedThemeSerializer()
    photos = PublicPhotoSerializer(many=True, source="ready_photos")

    class Meta:
        model = Memorial
        fields = (
            "short_code",
            "first_name",
            "last_name",
            "middle_name",
            "birth_date",
            "birth_date_precision",
            "death_date",
            "death_date_precision",
            "description",
            "language",
            "published_at",
            "theme",
            "photos",
        )
