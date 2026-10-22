import copy
import posixpath

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models

from apps.themes.schema import validate_asset_refs, validate_tokens


def theme_preview_path(instance: "Theme", filename: str) -> str:
    return posixpath.join("themes", instance.key, "preview", filename)


def theme_asset_path(instance: "ThemeAsset", filename: str) -> str:
    return posixpath.join("themes", instance.theme.key, "assets", filename)


class Theme(models.Model):
    class Category(models.TextChoices):
        NEUTRAL = "neutral", "Neutral"
        ISLAMIC = "islamic", "Islamic"
        CHRISTIAN = "christian", "Christian"
        SECULAR = "secular", "Secular"

    key = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=100)  # переводимое, см. translation.py
    category = models.CharField(max_length=16, choices=Category.choices)
    # Дублирует tokens["layout"] для фильтрации; заполняется в save().
    layout_key = models.CharField(max_length=32, editable=False, db_index=True)
    tokens = models.JSONField()
    preview_image = models.ImageField(upload_to=theme_preview_path, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    # Растёт при каждом изменении tokens.
    version = models.PositiveIntegerField(default=1, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "id")

    def __str__(self) -> str:
        return self.key

    def save(self, *args, **kwargs) -> None:
        # Структуру проверяем всегда, даже в обход форм. Ссылки на ассеты — в clean()
        # и сериализаторе: при создании темы с ассетами (админка) их ещё нет в базе.
        self.validate_tokens()
        self.layout_key = self.tokens["layout"]
        loaded = getattr(self, "_loaded_tokens", None)
        if self.pk is not None and loaded is not None and loaded != self.tokens:
            self.version += 1
        super().save(*args, **kwargs)
        self._loaded_tokens = copy.deepcopy(self.tokens)

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._loaded_tokens = copy.deepcopy(instance.tokens)
        return instance

    def asset_kinds(self) -> dict[str, str]:
        if self.pk is None:
            return {}
        return dict(self.assets.values_list("key", "kind"))

    def clean(self) -> None:
        super().clean()
        # Админка выставляет флаг и проверяет ссылки по данным inline-формсета.
        deferred = getattr(self, "defer_asset_refs_check", False)
        self.validate_tokens(None if deferred else self.asset_kinds())

    def validate_tokens(self, asset_kinds: dict[str, str] | None = None) -> None:
        """Структура tokens; при переданных `asset_kinds` — ещё и ссылки на ассеты."""
        errors = validate_tokens(self.tokens)
        if not errors and asset_kinds is not None:
            errors = validate_asset_refs(self.tokens, asset_kinds)
        if errors:
            raise ValidationError({"tokens": errors})


class ThemeAsset(models.Model):
    class Kind(models.TextChoices):
        BACKGROUND = "background", "Background"
        ORNAMENT = "ornament", "Ornament"
        FRAME = "frame", "Frame"
        ICON = "icon", "Icon"

    theme = models.ForeignKey(Theme, on_delete=models.CASCADE, related_name="assets")
    key = models.SlugField(max_length=64)
    file = models.FileField(
        upload_to=theme_asset_path,
        validators=[FileExtensionValidator(["svg", "png", "jpg", "jpeg", "webp"])],
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)

    class Meta:
        ordering = ("theme", "key")
        constraints = (
            models.UniqueConstraint(fields=("theme", "key"), name="unique_theme_asset_key"),
        )

    def __str__(self) -> str:
        return f"{self.theme.key}/{self.key}"
