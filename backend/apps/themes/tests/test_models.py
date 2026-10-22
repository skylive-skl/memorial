import pytest
from django.core.exceptions import ValidationError
from django.utils import translation

from apps.themes.models import Theme
from apps.themes.tests.factories import ThemeAssetFactory, ThemeFactory, make_tokens

pytestmark = pytest.mark.django_db


def test_invalid_tokens_are_not_saved():
    theme = ThemeFactory.build(tokens=make_tokens(layout="unknown"))

    with pytest.raises(ValidationError) as exc:
        theme.save()

    assert "tokens" in exc.value.message_dict
    assert not Theme.objects.exists()


def test_invalid_tokens_update_is_not_saved():
    theme = ThemeFactory()
    theme.tokens["colors"]["accent"] = "not-a-color"

    with pytest.raises(ValidationError):
        theme.save()

    theme.refresh_from_db()
    assert theme.tokens["colors"]["accent"] == "#8C6D3F"


def test_layout_key_filled_from_tokens():
    theme = ThemeFactory(tokens=make_tokens(layout="gallery", layoutOptions={}))

    assert theme.layout_key == "gallery"
    theme.tokens["layout"] = "classic"
    theme.save()
    theme.refresh_from_db()
    assert theme.layout_key == "classic"


class TestVersion:
    def test_starts_at_one(self):
        assert ThemeFactory().version == 1

    def test_incremented_when_tokens_change(self):
        theme = Theme.objects.get(pk=ThemeFactory().pk)
        theme.tokens["radius"] = "4px"
        theme.save()

        assert theme.version == 2
        theme.tokens["radius"] = "8px"
        theme.save()
        theme.refresh_from_db()
        assert theme.version == 3

    def test_not_incremented_on_other_changes(self):
        theme = Theme.objects.get(pk=ThemeFactory().pk)
        theme.sort_order = 10
        theme.is_active = False
        theme.save()

        theme.refresh_from_db()
        assert theme.version == 1


class TestCleanAssetRefs:
    def test_reference_to_missing_asset(self):
        theme = ThemeFactory()
        theme.tokens["ornaments"]["divider"] = "divider-1"

        with pytest.raises(ValidationError) as exc:
            theme.full_clean()

        assert exc.value.message_dict["tokens"] == [
            "tokens.ornaments.divider: asset 'divider-1' does not exist in this theme"
        ]

    def test_reference_to_asset_of_other_theme(self):
        ThemeAssetFactory(key="divider-1")
        theme = ThemeFactory()
        theme.tokens["ornaments"]["divider"] = "divider-1"

        with pytest.raises(ValidationError):
            theme.full_clean()

    def test_reference_to_existing_asset(self):
        theme = ThemeFactory()
        ThemeAssetFactory(theme=theme, key="divider-1")
        theme.tokens["ornaments"]["divider"] = "divider-1"

        theme.full_clean()


def test_asset_key_unique_within_theme():
    asset = ThemeAssetFactory(key="bg")
    ThemeAssetFactory(key="bg")  # в другой теме — можно

    with pytest.raises(ValidationError):
        ThemeAssetFactory.build(theme=asset.theme, key="bg").full_clean()


def test_asset_extension_validated():
    asset = ThemeAssetFactory.build(theme=ThemeFactory())
    asset.file.name = "evil.html"

    with pytest.raises(ValidationError) as exc:
        asset.full_clean()

    assert "file" in exc.value.message_dict


def test_name_is_translatable():
    theme = ThemeFactory(name_ru="Классика", name_uz="Klassika", name_en="Classic")

    with translation.override("uz"):
        assert theme.name == "Klassika"
    with translation.override("en"):
        assert theme.name == "Classic"


def test_name_falls_back_to_russian():
    theme = ThemeFactory(name_ru="Классика", name_uz=None, name_en=None)

    with translation.override("uz"):
        assert theme.name == "Классика"
