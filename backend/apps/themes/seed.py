"""Стартовый каталог тем из `fixtures/themes.json`.

Тот же JSON читает тест фронта (zod-схема), поэтому формат tokens здесь — эталонный.
"""

import copy
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models.fields.files import FieldFile
from PIL import Image, ImageDraw

from apps.themes.models import Theme, ThemeAsset

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
THEMES_FILE = FIXTURES_DIR / "themes.json"
ASSETS_DIR = FIXTURES_DIR / "assets"

LANGUAGES = ("ru", "uz", "en")


def load_theme_fixtures() -> list[dict[str, Any]]:
    return json.loads(THEMES_FILE.read_text(encoding="utf-8"))


@dataclass
class SeedResult:
    key: str
    status: str  # created | updated | unchanged | skipped


def seed_themes(*, update: bool = False) -> list[SeedResult]:
    """Создаёт недостающие темы. С `update=True` приводит существующие к фикстурам.

    Повторный запуск ничего не меняет: файлы перезаливаются только при изменении
    содержимого, `version` растёт только при изменении tokens.
    """
    return [_seed_theme(fixture, update=update) for fixture in load_theme_fixtures()]


@transaction.atomic
def _seed_theme(fixture: dict[str, Any], *, update: bool) -> SeedResult:
    key = fixture["key"]
    theme = Theme.objects.filter(key=key).first()
    if theme is not None and not update:
        return SeedResult(key, "skipped")

    created = theme is None
    if created:
        theme = Theme(key=key)

    values = {
        **{f"name_{lang}": fixture["name"][lang] for lang in LANGUAGES},
        "category": fixture["category"],
        "sort_order": fixture["sort_order"],
        "tokens": copy.deepcopy(fixture["tokens"]),
        "is_active": True,
    }
    changed = created or any(getattr(theme, field) != value for field, value in values.items())
    for field, value in values.items():
        setattr(theme, field, value)
    if changed:
        theme.save()

    changed |= _sync_assets(theme, fixture["assets"])
    changed |= _replace_file_if_differs(
        theme.preview_image, "preview.png", render_preview(fixture["tokens"])
    )

    theme.full_clean()  # в т. ч. ссылки tokens → ассеты
    if created:
        return SeedResult(key, "created")
    return SeedResult(key, "updated" if changed else "unchanged")


def _sync_assets(theme: Theme, asset_fixtures: list[dict[str, str]]) -> bool:
    changed = False
    existing = {asset.key: asset for asset in theme.assets.all()}
    for item in asset_fixtures:
        asset = existing.pop(item["key"], None) or ThemeAsset(theme=theme, key=item["key"])
        content = (ASSETS_DIR / item["file"]).read_bytes()
        if asset.kind != item["kind"]:
            asset.kind = item["kind"]
            changed = True
            if asset.pk:
                asset.save(update_fields=["kind"])
        changed |= _replace_file_if_differs(asset.file, item["file"], content)
    for stale in existing.values():
        stale.file.delete(save=False)
        stale.delete()
        changed = True
    return changed


def _replace_file_if_differs(field_file: FieldFile, name: str, content: bytes) -> bool:
    if field_file and _read(field_file) == content:
        return False
    if field_file:
        field_file.delete(save=False)
    field_file.save(name, ContentFile(content), save=True)
    return True


def _read(field_file: FieldFile) -> bytes | None:
    try:
        with field_file.open("rb") as f:
            return f.read()
    except (FileNotFoundError, OSError):
        return None


def render_preview(tokens: dict[str, Any]) -> bytes:
    """Схематичное превью темы (заглушка, пока нет настоящих скриншотов)."""
    colors = tokens["colors"]
    image = Image.new("RGB", (600, 400), colors["background"])
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (150, 30, 450, 370), radius=12, fill=colors["surface"], outline=colors["border"], width=2
    )
    draw.ellipse((255, 60, 345, 170), fill=colors["muted"])
    draw.rectangle((210, 195, 390, 211), fill=colors["text"])
    draw.rectangle((250, 225, 350, 233), fill=colors["muted"])
    draw.rectangle((270, 252, 330, 255), fill=colors["accent"])
    for i, width in enumerate((200, 180, 190)):
        y = 280 + i * 18
        draw.rectangle((300 - width // 2, y, 300 + width // 2, y + 6), fill=colors["muted"])
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
