import pytest

from apps.themes.tests.factories import ThemeAssetFactory, ThemeFactory

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/themes/"


def test_catalog_is_public_and_lists_only_active_sorted(api_client):
    ThemeFactory(key="b", sort_order=20)
    ThemeFactory(key="a", sort_order=10)
    ThemeFactory(key="hidden", is_active=False)

    response = api_client.get(LIST_URL)

    assert response.status_code == 200
    assert [t["key"] for t in response.data] == ["a", "b"]


def test_filter_by_category(api_client):
    ThemeFactory(key="green", category="islamic")
    ThemeFactory(key="white", category="neutral")

    response = api_client.get(LIST_URL, {"category": "islamic"})

    assert [t["key"] for t in response.data] == ["green"]


def test_detail_with_assets_and_all_names(api_client):
    theme = ThemeFactory(key="emerald", name_ru="Изумрудная", name_uz="Zumrad", name_en=None)
    ThemeAssetFactory(theme=theme, key="divider")

    response = api_client.get(f"{LIST_URL}emerald/")

    assert response.status_code == 200
    assert response.data["name"] == {"ru": "Изумрудная", "uz": "Zumrad", "en": "Изумрудная"}
    assert response.data["tokens"] == theme.tokens
    assert response.data["assets"][0]["key"] == "divider"
    assert response.data["assets"][0]["url"].startswith("http")


def test_inactive_theme_detail_is_404(api_client):
    ThemeFactory(key="hidden", is_active=False)

    assert api_client.get(f"{LIST_URL}hidden/").status_code == 404


def test_catalog_is_read_only(api_client, admin_user):
    api_client.force_authenticate(admin_user)

    assert api_client.post(LIST_URL, {}).status_code == 405
