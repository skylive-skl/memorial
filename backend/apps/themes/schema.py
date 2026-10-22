"""JSON Schema для `Theme.tokens` (schemaVersion 1).

Зеркало на фронте — `frontend/src/themes/schema.ts` (zod). Меняются только вместе.
"""

from collections.abc import Mapping
from typing import Any

from jsonschema import Draft202012Validator

# Шрифты загружаются через next/font, поэтому список фиксирован в коде (фронт и бэк).
# Все проверены на кириллицу, узбекские «ʻ» (U+02BB), «ʼ» (U+02BC) и узбекскую кириллицу.
# Не подходят (нет U+02BB): Roboto, Open Sans, PT Serif, PT Sans, Manrope, Prata.
FONTS = (
    "Playfair Display",
    "Cormorant Garamond",
    "EB Garamond",
    "Lora",
    "Merriweather",
    "Noto Serif",
    "Spectral",
    "Inter",
    "Montserrat",
    "Noto Sans",
)

# hex (#rgb, #rrggbb, #rrggbbaa) или rgb()/rgba() с числами.
COLOR_PATTERN = (
    r"^(#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})"
    r"|rgba?\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*(,\s*(0|1|0?\.\d+)\s*)?\))$"
)
# Без «;», «{», «}», кавычек и «:» — значение попадает в CSS-переменную и не должно
# выходить за пределы декларации.
GRADIENT_PATTERN = r"^(linear|radial)-gradient\([a-zA-Z0-9#%.,()\s-]+\)$"
RADIUS_PATTERN = r"^(0|\d{1,3}px|\d{1,2}(\.\d{1,2})?rem)$"
ASSET_KEY_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"

_color = {"type": "string", "pattern": COLOR_PATTERN}
_asset_ref = {"type": ["string", "null"], "pattern": ASSET_KEY_PATTERN}
_font = {"type": "string", "enum": list(FONTS)}

# Опции конкретных layout'ов. Ключи — те же, что в реестре фронта (src/themes/registry.ts).
LAYOUT_OPTIONS_SCHEMAS: dict[str, dict[str, Any]] = {
    "classic": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "photoShape": {"enum": ["oval", "circle", "rounded", "square"]},
            "gallery": {"enum": ["grid", "masonry"]},
        },
    },
    "gallery": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "galleryStyle": {"enum": ["slider", "masonry"]},
            "descriptionPosition": {"enum": ["side", "below"]},
        },
    },
}

TOKENS_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["schemaVersion", "layout", "colors", "fonts", "background", "radius"],
    "properties": {
        "schemaVersion": {"const": 1},
        "layout": {"enum": list(LAYOUT_OPTIONS_SCHEMAS)},
        "layoutOptions": {"type": "object"},
        "colors": {
            "type": "object",
            "additionalProperties": False,
            "required": ["background", "surface", "text", "muted", "accent", "border"],
            "properties": {
                name: _color
                for name in ("background", "surface", "text", "muted", "accent", "border")
            },
        },
        "fonts": {
            "type": "object",
            "additionalProperties": False,
            "required": ["heading", "body"],
            "properties": {"heading": _font, "body": _font},
        },
        "background": {
            "type": "object",
            "additionalProperties": False,
            "required": ["type"],
            "properties": {
                "type": {"enum": ["color", "image", "gradient"]},
                "asset": _asset_ref,
                "value": {"type": ["string", "null"]},
                "overlay": {"anyOf": [_color, {"type": "null"}]},
            },
            "allOf": [
                {
                    "if": {"required": ["type"], "properties": {"type": {"const": "image"}}},
                    "then": {
                        "required": ["asset"],
                        "properties": {"asset": {"type": "string"}},
                    },
                },
                {
                    "if": {"required": ["type"], "properties": {"type": {"const": "gradient"}}},
                    "then": {
                        "required": ["value"],
                        "properties": {"value": {"type": "string", "pattern": GRADIENT_PATTERN}},
                    },
                },
                {
                    # null — цвет фона берётся из colors.background.
                    "if": {"required": ["type"], "properties": {"type": {"const": "color"}}},
                    "then": {"properties": {"value": {"anyOf": [_color, {"type": "null"}]}}},
                },
            ],
        },
        "ornaments": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"top": _asset_ref, "divider": _asset_ref, "photoFrame": _asset_ref},
        },
        "radius": {"type": "string", "pattern": RADIUS_PATTERN},
    },
}

_tokens_validator = Draft202012Validator(TOKENS_SCHEMA)
_layout_validators = {
    key: Draft202012Validator(schema) for key, schema in LAYOUT_OPTIONS_SCHEMAS.items()
}

# Какой kind ассета допустим в каждой ссылке из tokens.
ASSET_REF_KINDS: dict[tuple[str, str], str] = {
    ("background", "asset"): "background",
    ("ornaments", "top"): "ornament",
    ("ornaments", "divider"): "ornament",
    ("ornaments", "photoFrame"): "frame",
}


def _format_path(prefix: str, path) -> str:
    return ".".join([prefix, *(str(p) for p in path)]) if path else prefix


def validate_tokens(tokens: Any) -> list[str]:
    """Ошибки структуры tokens в виде «путь: сообщение». Пустой список — tokens валидны."""
    errors = [
        f"{_format_path('tokens', e.absolute_path)}: {e.message}"
        for e in sorted(_tokens_validator.iter_errors(tokens), key=lambda e: list(e.path))
    ]
    if errors:
        return errors

    validator = _layout_validators[tokens["layout"]]
    return [
        f"{_format_path('tokens.layoutOptions', e.absolute_path)}: {e.message}"
        for e in validator.iter_errors(tokens.get("layoutOptions", {}))
    ]


def validate_asset_refs(tokens: Mapping[str, Any], assets: Mapping[str, str]) -> list[str]:
    """Проверяет, что ссылки на ассеты в tokens указывают на ассеты этой темы нужного kind.

    `assets` — словарь `key -> kind` ассетов темы. Предполагается, что структура tokens
    уже проверена `validate_tokens`.
    """
    errors = []
    for (section, field), expected_kind in ASSET_REF_KINDS.items():
        ref = tokens.get(section, {}).get(field)
        if ref is None:
            continue
        path = f"tokens.{section}.{field}"
        if ref not in assets:
            errors.append(f"{path}: asset '{ref}' does not exist in this theme")
        elif assets[ref] != expected_kind:
            errors.append(
                f"{path}: asset '{ref}' has kind '{assets[ref]}', expected '{expected_kind}'"
            )
    return errors
