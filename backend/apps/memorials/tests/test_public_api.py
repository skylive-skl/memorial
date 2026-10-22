import pytest
from django.core.files.base import ContentFile
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.memorials.models import Memorial, Photo
from apps.memorials.tasks import process_photo
from apps.memorials.tests.factories import MemorialFactory
from apps.memorials.tests.images import jpeg_bytes
from apps.themes.tests.factories import ThemeAssetFactory, ThemeFactory, make_tokens

pytestmark = pytest.mark.django_db


def public_url(code: str) -> str:
    return f"/api/v1/public/m/{code}/"


def add_photo(memorial: Memorial, *, ready: bool = True, **kwargs) -> Photo:
    photo = Photo(memorial=memorial, **kwargs)
    photo.original.save("p.jpg", ContentFile(jpeg_bytes(gps=True)))
    if ready:
        process_photo(photo.pk)
        photo.refresh_from_db()
    return photo


@pytest.fixture
def published() -> Memorial:
    theme = ThemeFactory(
        key="emerald",
        tokens=make_tokens(
            background={"type": "image", "asset": "bg", "value": None, "overlay": None},
            ornaments={"top": "star", "divider": None, "photoFrame": None},
        ),
    )
    ThemeAssetFactory(theme=theme, key="bg", kind="background")
    ThemeAssetFactory(theme=theme, key="star", kind="ornament")
    memorial = MemorialFactory(
        theme=theme,
        owner__email="owner-secret@example.com",
        middle_name="Каримович",
        birth_date="1948-03-12",
        birth_date_precision="month",
        death_date="2020-07-01",
        description="Строка 1\nСтрока 2",
        language="uz",
    )
    memorial.publish()
    return memorial


def test_returns_everything_needed_to_render(api_client, published):
    cover = add_photo(published, is_cover=True, order=0, caption="Портрет")
    add_photo(published, order=1)

    response = api_client.get(public_url(published.short_code))

    assert response.status_code == 200
    data = response.json()
    assert set(data) == {
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
    }
    assert data["short_code"] == published.short_code
    assert data["birth_date"] == "1948-03-01"
    assert data["birth_date_precision"] == "month"
    assert data["description"] == "Строка 1\nСтрока 2"
    assert data["language"] == "uz"

    assert set(data["theme"]) == {"key", "version", "tokens", "assets"}
    assert data["theme"]["tokens"] == published.theme.tokens
    assert set(data["theme"]["assets"]) == {"bg", "star"}
    assert all(url.startswith("http") for url in data["theme"]["assets"].values())

    assert [p["caption"] for p in data["photos"]] == ["Портрет", ""]
    first = data["photos"][0]
    assert set(first) == {"caption", "is_cover", "width", "height", "variants"}
    assert first["is_cover"] is True
    assert set(first["variants"]) == {"thumb", "medium", "large"}
    assert first["variants"]["large"].endswith(f"photos/{cover.folder}/large.webp")


def test_no_private_data_leaks(api_client, published):
    photo = add_photo(published)

    body = api_client.get(public_url(published.short_code)).content.decode()

    assert "owner-secret@example.com" not in body
    assert "original" not in body
    assert photo.original.name not in body
    assert '"id"' not in body
    assert "owner" not in body
    assert "theme_overrides" not in body


def test_only_processed_photos(api_client, published):
    add_photo(published, order=0)
    add_photo(published, ready=False, order=1)
    failed = add_photo(published, ready=False, order=2)
    Photo.objects.filter(pk=failed.pk).update(processing_status="failed")

    data = api_client.get(public_url(published.short_code)).json()

    assert len(data["photos"]) == 1


def test_photos_in_page_order(api_client, published):
    add_photo(published, order=2, caption="c")
    add_photo(published, order=0, caption="a")
    add_photo(published, order=1, caption="b")

    data = api_client.get(public_url(published.short_code)).json()

    assert [p["caption"] for p in data["photos"]] == ["a", "b", "c"]


def test_draft_and_unknown_code_give_identical_404(api_client):
    draft = MemorialFactory()

    draft_response = api_client.get(public_url(draft.short_code))
    unknown_response = api_client.get(public_url("ZZZZZZZZ"))

    assert draft_response.status_code == unknown_response.status_code == 404
    assert draft_response.content == unknown_response.content
    assert b"Memorial" not in unknown_response.content  # без внутреннего имени модели


def test_unpublished_page_is_404_again(api_client, published):
    published.unpublish()

    assert api_client.get(public_url(published.short_code)).status_code == 404


def test_stale_auth_cookie_does_not_break_page(api_client, published):
    api_client.cookies["access_token"] = "expired-garbage"

    assert api_client.get(public_url(published.short_code)).status_code == 200


def test_inactive_theme_still_renders(api_client, published):
    published.theme.is_active = False
    published.theme.save()

    response = api_client.get(public_url(published.short_code))

    assert response.status_code == 200
    assert response.json()["theme"]["key"] == "emerald"


def test_theme_version_exposed(api_client, published):
    published.theme.tokens["radius"] = "0"
    published.theme.save()

    data = api_client.get(public_url(published.short_code)).json()

    assert data["theme"]["version"] == 2


def test_query_count_does_not_grow_with_photos_and_assets(api_client, published):
    add_photo(published)

    with CaptureQueriesContext(connection) as few:
        api_client.get(public_url(published.short_code))
    for _ in range(3):
        add_photo(published)
    ThemeAssetFactory(theme=published.theme, key="extra", kind="icon")
    with CaptureQueriesContext(connection) as many:
        api_client.get(public_url(published.short_code))

    assert len(many) == len(few)


def test_read_only(api_client, published):
    response = api_client.post(public_url(published.short_code), {}, format="json")

    assert response.status_code == 405
