import json

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from modeltranslation.admin import TranslationAdmin

from apps.themes.models import Theme, ThemeAsset
from apps.themes.schema import FONTS, LAYOUT_OPTIONS_SCHEMAS, validate_asset_refs, validate_tokens

# Стартовые tokens для новой темы — чтобы не писать JSON с нуля.
TOKENS_TEMPLATE = {
    "schemaVersion": 1,
    "layout": "classic",
    "layoutOptions": {"photoShape": "oval", "gallery": "grid"},
    "colors": {
        "background": "#F7F5F0",
        "surface": "#FFFFFF",
        "text": "#2B2B2B",
        "muted": "#7A7468",
        "accent": "#8C6D3F",
        "border": "#E2DDD3",
    },
    "fonts": {"heading": "Playfair Display", "body": "Inter"},
    "background": {"type": "color", "asset": None, "value": None, "overlay": None},
    "ornaments": {"top": None, "divider": None, "photoFrame": None},
    "radius": "12px",
}

TOKENS_HELP = format_html(
    "JSON по схеме из docs/PLAN.md, раздел «Формат темы».<br>"
    "Layout'ы: {}. Шрифты: {}.<br>"
    "Ссылки на ассеты (<code>background.asset</code>, <code>ornaments.*</code>) — ключи "
    "ассетов этой темы ниже: фон — kind <code>background</code>, орнаменты — "
    "<code>ornament</code>, рамка фото — <code>frame</code>.",
    ", ".join(LAYOUT_OPTIONS_SCHEMAS),
    ", ".join(FONTS),
)


class PrettyJSONField(forms.JSONField):
    def prepare_value(self, value):
        if isinstance(value, str):  # невалидный ввод показываем как есть
            return value
        return json.dumps(value, ensure_ascii=False, indent=2)


class ThemeAdminForm(forms.ModelForm):
    tokens = PrettyJSONField(
        initial=TOKENS_TEMPLATE,
        help_text=TOKENS_HELP,
        widget=forms.Textarea(
            attrs={
                "rows": 32,
                "cols": 100,
                "style": "font-family: monospace;",
                "spellcheck": "false",
            }
        ),
    )

    class Meta:
        model = Theme
        fields = ("key", "name", "category", "is_active", "sort_order", "preview_image", "tokens")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ссылки на ассеты проверяет ThemeAssetInlineFormSet: ассеты создаются/удаляются
        # в той же форме и в базе их ещё нет.
        self.instance.defer_asset_refs_check = True


class ThemeAssetInlineFormSet(forms.BaseInlineFormSet):
    def clean(self) -> None:
        super().clean()
        theme = self.instance
        if theme.tokens is None or validate_tokens(theme.tokens):
            return  # ошибки структуры уже показаны у поля tokens
        assets = {
            form.cleaned_data["key"]: form.cleaned_data["kind"]
            for form in self.forms
            if form.cleaned_data
            and not self._should_delete_form(form)
            and form.cleaned_data.get("key")
        }
        errors = validate_asset_refs(theme.tokens, assets)
        if errors:
            raise ValidationError(
                [
                    "Tokens ссылаются на отсутствующие ассеты (нельзя удалить или переименовать "
                    "ассет, который используется):",
                    *errors,
                ]
            )


def _thumbnail(file, height: int) -> str:
    if not file:
        return "—"
    return format_html(
        '<img src="{}" style="height:{}px; max-width:{}px; object-fit:contain;" alt="">',
        file.url,
        height,
        height * 3,
    )


class ThemeAssetInline(admin.TabularInline):
    model = ThemeAsset
    formset = ThemeAssetInlineFormSet
    extra = 1
    fields = ("key", "kind", "file", "preview")
    readonly_fields = ("preview",)

    @admin.display(description="Превью")
    def preview(self, obj: ThemeAsset) -> str:
        return _thumbnail(obj.file, 48)


@admin.register(Theme)
class ThemeAdmin(TranslationAdmin):
    form = ThemeAdminForm
    inlines = (ThemeAssetInline,)
    list_display = (
        "preview_thumbnail",
        "key",
        "name",
        "category",
        "layout_key",
        "is_active",
        "sort_order",
        "version",
        "updated_at",
    )
    list_display_links = ("preview_thumbnail", "key")
    list_editable = ("is_active", "sort_order")
    list_filter = ("category", "is_active", "layout_key")
    search_fields = ("key", "name_ru", "name_uz", "name_en")
    readonly_fields = ("preview_large", "layout_key", "version", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("key", "name", "category", "is_active", "sort_order")}),
        ("Превью", {"fields": ("preview_image", "preview_large")}),
        ("Оформление", {"fields": ("tokens", "layout_key", "version")}),
        ("Служебное", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="Превью")
    def preview_thumbnail(self, obj: Theme) -> str:
        return _thumbnail(obj.preview_image, 48)

    @admin.display(description="Текущее превью")
    def preview_large(self, obj: Theme) -> str:
        return _thumbnail(obj.preview_image, 240)
