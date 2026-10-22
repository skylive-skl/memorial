import pytest

from apps.themes.serializers import ThemeSerializer
from apps.themes.tests.factories import ThemeAssetFactory, ThemeFactory, make_tokens

pytestmark = pytest.mark.django_db


def test_rejects_invalid_tokens():
    serializer = ThemeSerializer(
        data={"key": "t", "name": "T", "category": "neutral", "tokens": make_tokens(radius="x")}
    )

    assert not serializer.is_valid()
    assert serializer.errors["tokens"][0].startswith("tokens.radius:")


def test_rejects_missing_asset_ref_on_create():
    tokens = make_tokens(ornaments={"top": "ornament-top"})
    serializer = ThemeSerializer(
        data={"key": "t", "name": "T", "category": "neutral", "tokens": tokens}
    )

    assert not serializer.is_valid()
    assert "does not exist" in serializer.errors["tokens"][0]


def test_accepts_existing_asset_ref_on_update():
    theme = ThemeFactory()
    ThemeAssetFactory(theme=theme, key="ornament-top")
    tokens = make_tokens(ornaments={"top": "ornament-top"})

    serializer = ThemeSerializer(theme, data={"tokens": tokens}, partial=True)

    assert serializer.is_valid(), serializer.errors


def test_output_contains_assets_with_urls():
    theme = ThemeFactory()
    ThemeAssetFactory(theme=theme, key="ornament-top")

    data = ThemeSerializer(theme).data

    assert data["layout_key"] == "classic"
    assert data["assets"][0]["key"] == "ornament-top"
    assert data["assets"][0]["url"].startswith("http")
