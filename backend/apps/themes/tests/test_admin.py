import html
import io
import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.themes.models import Theme, ThemeAsset
from apps.themes.tests.factories import ThemeAssetFactory, ThemeFactory, make_tokens

pytestmark = pytest.mark.django_db

ADD_URL = "/admin/themes/theme/add/"
CHANGELIST_URL = "/admin/themes/theme/"


def png_upload(name: str = "preview.png") -> SimpleUploadedFile:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def svg_upload(name: str = "ornament.svg") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml")


def theme_form_data(tokens, **overrides) -> dict:
    data = {
        "key": "new-theme",
        "name_ru": "Новая тема",
        "name_uz": "Yangi mavzu",
        "name_en": "New theme",
        "category": "islamic",
        "is_active": "on",
        "sort_order": "5",
        "tokens": tokens if isinstance(tokens, str) else json.dumps(tokens),
        "assets-TOTAL_FORMS": "0",
        "assets-INITIAL_FORMS": "0",
        "assets-MIN_NUM_FORMS": "0",
        "assets-MAX_NUM_FORMS": "1000",
    }
    data.update(overrides)
    return data


def with_new_asset(data: dict, index: int, key: str, kind: str, file) -> dict:
    data[f"assets-{index}-key"] = key
    data[f"assets-{index}-kind"] = kind
    data[f"assets-{index}-file"] = file
    data["assets-TOTAL_FORMS"] = str(index + 1)
    return data


def change_form_data(theme: Theme, tokens=None) -> dict:
    """Данные формы изменения с текущими ассетами темы."""
    data = theme_form_data(
        tokens if tokens is not None else theme.tokens,
        key=theme.key,
        name_ru=theme.name_ru,
        category=theme.category,
    )
    assets = list(theme.assets.all())
    for i, asset in enumerate(assets):
        data[f"assets-{i}-id"] = str(asset.id)
        data[f"assets-{i}-theme"] = str(theme.id)
        data[f"assets-{i}-key"] = asset.key
        data[f"assets-{i}-kind"] = asset.kind
    data["assets-TOTAL_FORMS"] = data["assets-INITIAL_FORMS"] = str(len(assets))
    return data


def form_errors(response) -> str:
    """Все ошибки формы и inline-формсетов одной строкой."""
    parts = [str(response.context["adminform"].form.errors)]
    parts += [str(fs.formset.non_form_errors()) for fs in response.context["inline_admin_formsets"]]
    parts += [str(fs.formset.errors) for fs in response.context["inline_admin_formsets"]]
    return html.unescape(" ".join(parts))


def test_changelist_with_filters(admin_client):
    ThemeFactory(key="islamic-green", category="islamic", is_active=True)
    ThemeFactory(key="neutral-white", category="neutral", is_active=False)

    response = admin_client.get(
        CHANGELIST_URL, {"category__exact": "islamic", "is_active__exact": "1"}
    )

    assert response.status_code == 200
    assert b"islamic-green" in response.content
    assert b"neutral-white" not in response.content


def test_add_form_prefilled_with_tokens_template(admin_client):
    response = admin_client.get(ADD_URL)

    assert response.status_code == 200
    content = html.unescape(response.content.decode())
    assert '"schemaVersion": 1' in content
    for lang in ("ru", "uz", "en"):
        assert f'name="name_{lang}"' in content


def test_create_theme_fully_through_admin(admin_client):
    tokens = make_tokens(
        background={"type": "image", "asset": "bg-main", "value": None, "overlay": None},
        ornaments={"top": "ornament-top", "divider": None, "photoFrame": None},
    )
    data = theme_form_data(tokens, preview_image=png_upload())
    with_new_asset(data, 0, "bg-main", "background", png_upload("bg.png"))
    with_new_asset(data, 1, "ornament-top", "ornament", svg_upload())

    response = admin_client.post(ADD_URL, data)

    assert response.status_code == 302, form_errors(response)
    theme = Theme.objects.get(key="new-theme")
    assert theme.name_ru == "Новая тема"
    assert theme.name_uz == "Yangi mavzu"
    assert theme.category == "islamic"
    assert theme.layout_key == "classic"
    assert theme.tokens == tokens
    assert theme.preview_image.name.startswith("themes/new-theme/preview/")
    assert dict(theme.assets.values_list("key", "kind")) == {
        "bg-main": "background",
        "ornament-top": "ornament",
    }


def test_invalid_json_shows_error(admin_client):
    response = admin_client.post(ADD_URL, theme_form_data('{"schemaVersion": 1,'))

    assert response.status_code == 200
    assert "tokens" in response.context["adminform"].form.errors
    assert not Theme.objects.exists()


def test_schema_error_shown_with_path(admin_client):
    tokens = make_tokens(colors={**make_tokens()["colors"], "text": "red"})

    response = admin_client.post(ADD_URL, theme_form_data(tokens))

    assert response.status_code == 200
    assert "tokens.colors.text" in str(response.context["adminform"].form.errors["tokens"])
    assert not Theme.objects.exists()


def test_reference_to_missing_asset_shows_error(admin_client):
    tokens = make_tokens(ornaments={"top": "ornament-top"})

    response = admin_client.post(ADD_URL, theme_form_data(tokens))

    assert response.status_code == 200
    assert "tokens.ornaments.top: asset 'ornament-top' does not exist" in form_errors(response)
    assert not Theme.objects.exists()


def test_reference_to_asset_of_wrong_kind_shows_error(admin_client):
    tokens = make_tokens(ornaments={"photoFrame": "frame-1"})
    data = with_new_asset(theme_form_data(tokens), 0, "frame-1", "ornament", svg_upload())

    response = admin_client.post(ADD_URL, data)

    assert response.status_code == 200
    assert "expected" in form_errors(response)


class TestUsedAssetProtection:
    @pytest.fixture
    def theme(self):
        theme = ThemeFactory()
        ThemeAssetFactory(theme=theme, key="divider-1")
        ThemeAssetFactory(theme=theme, key="unused")
        theme.tokens["ornaments"]["divider"] = "divider-1"
        theme.save()
        return theme

    def _change_url(self, theme):
        return f"/admin/themes/theme/{theme.id}/change/"

    def _index_of(self, data, key):
        return next(k.split("-")[1] for k, v in data.items() if k.endswith("-key") and v == key)

    def test_used_asset_cannot_be_deleted(self, admin_client, theme):
        data = change_form_data(theme)
        data[f"assets-{self._index_of(data, 'divider-1')}-DELETE"] = "on"

        response = admin_client.post(self._change_url(theme), data)

        assert response.status_code == 200
        assert "divider-1" in form_errors(response)
        assert theme.assets.filter(key="divider-1").exists()

    def test_used_asset_cannot_be_renamed(self, admin_client, theme):
        data = change_form_data(theme)
        data[f"assets-{self._index_of(data, 'divider-1')}-key"] = "divider-2"

        response = admin_client.post(self._change_url(theme), data)

        assert response.status_code == 200
        assert theme.assets.filter(key="divider-1").exists()

    def test_unused_asset_can_be_deleted(self, admin_client, theme):
        data = change_form_data(theme)
        data[f"assets-{self._index_of(data, 'unused')}-DELETE"] = "on"

        response = admin_client.post(self._change_url(theme), data)

        assert response.status_code == 302, form_errors(response)
        assert not ThemeAsset.objects.filter(key="unused").exists()

    def test_asset_can_be_replaced_in_one_submit(self, admin_client, theme):
        tokens = {**theme.tokens, "ornaments": {**theme.tokens["ornaments"], "divider": "new-div"}}
        data = change_form_data(theme, tokens)
        data[f"assets-{self._index_of(data, 'divider-1')}-DELETE"] = "on"
        with_new_asset(data, int(data["assets-TOTAL_FORMS"]), "new-div", "ornament", svg_upload())

        response = admin_client.post(self._change_url(theme), data)

        assert response.status_code == 302, form_errors(response)
        theme.refresh_from_db()
        assert theme.tokens["ornaments"]["divider"] == "new-div"
        assert theme.version == 3
        assert set(theme.assets.values_list("key", flat=True)) == {"new-div", "unused"}
