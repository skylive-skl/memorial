import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import PASSWORD, UserFactory
from apps.memorials.models import Memorial
from apps.memorials.tests.factories import MemorialFactory
from apps.themes.tests.factories import ThemeFactory

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/memorials/"


def detail_url(memorial: Memorial, suffix: str = "") -> str:
    return f"{LIST_URL}{memorial.id}/{suffix}"


@pytest.fixture
def user():
    return UserFactory(preferred_language="uz")


@pytest.fixture
def client(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


class TestAuth:
    @pytest.mark.parametrize("method", ["get", "post"])
    def test_anonymous_gets_401(self, api_client, method):
        assert getattr(api_client, method)(LIST_URL).status_code == 401

    def test_anonymous_detail_gets_401(self, api_client):
        assert api_client.get(detail_url(MemorialFactory())).status_code == 401


class TestOwnership:
    def test_list_contains_only_own(self, client, user):
        own = MemorialFactory(owner=user)
        MemorialFactory()

        response = client.get(LIST_URL)

        assert response.status_code == 200
        assert [m["id"] for m in response.data] == [own.id]

    @pytest.mark.parametrize(
        ("method", "suffix"),
        [
            ("get", ""),
            ("patch", ""),
            ("put", ""),
            ("delete", ""),
            ("post", "publish/"),
            ("post", "unpublish/"),
        ],
    )
    def test_foreign_memorial_is_404(self, client, method, suffix):
        foreign = MemorialFactory()

        response = getattr(client, method)(detail_url(foreign, suffix), {}, format="json")

        assert response.status_code == 404
        foreign.refresh_from_db()
        assert foreign.status == Memorial.Status.DRAFT


class TestCreate:
    def test_defaults_theme_and_language(self, client, user):
        ThemeFactory(key="second", sort_order=20)
        first = ThemeFactory(key="first", sort_order=10)
        ThemeFactory(key="inactive", sort_order=0, is_active=False)

        response = client.post(LIST_URL, {"first_name": "Иван", "last_name": "Петров"})

        assert response.status_code == 201, response.data
        assert response.data["theme"] == first.key
        assert response.data["language"] == "uz"
        assert response.data["status"] == "draft"
        assert len(response.data["short_code"]) == 8
        assert Memorial.objects.get(id=response.data["id"]).owner == user

    def test_explicit_theme_and_language(self, client):
        theme = ThemeFactory(key="chosen")

        response = client.post(
            LIST_URL,
            {"first_name": "A", "last_name": "B", "theme": "chosen", "language": "en"},
        )

        assert response.status_code == 201
        assert response.data["theme"] == theme.key
        assert response.data["language"] == "en"

    def test_inactive_theme_rejected(self, client):
        ThemeFactory(key="old", is_active=False)

        response = client.post(LIST_URL, {"first_name": "A", "last_name": "B", "theme": "old"})

        assert response.status_code == 400
        assert "theme" in response.data

    def test_no_active_themes(self, client):
        response = client.post(LIST_URL, {"first_name": "A", "last_name": "B"})

        assert response.status_code == 400
        assert "theme" in response.data

    def test_read_only_fields_ignored(self, client):
        ThemeFactory()

        response = client.post(
            LIST_URL,
            {
                "first_name": "A",
                "last_name": "B",
                "short_code": "MANUAL22",
                "status": "published",
                "theme_overrides": {"x": 1},
            },
            format="json",
        )

        assert response.status_code == 201
        assert response.data["short_code"] != "MANUAL22"
        assert response.data["status"] == "draft"
        assert response.data["theme_overrides"] == {}

    def test_dates_normalized_by_precision(self, client):
        ThemeFactory()

        response = client.post(
            LIST_URL,
            {
                "first_name": "A",
                "last_name": "B",
                "birth_date": "1950-05-17",
                "birth_date_precision": "year",
                "death_date": "2001-03-09",
                "death_date_precision": "month",
            },
        )

        assert response.status_code == 201
        assert response.data["birth_date"] == "1950-01-01"
        assert response.data["death_date"] == "2001-03-01"

    def test_death_before_birth_rejected(self, client):
        ThemeFactory()

        response = client.post(
            LIST_URL,
            {
                "first_name": "A",
                "last_name": "B",
                "birth_date": "1950-05-17",
                "death_date": "1940-01-01",
            },
        )

        assert response.status_code == 400
        assert "death_date" in response.data

    def test_description_too_long(self, client):
        ThemeFactory()

        response = client.post(
            LIST_URL, {"first_name": "A", "last_name": "B", "description": "x" * 10_001}
        )

        assert response.status_code == 400
        assert "description" in response.data


class TestUpdate:
    def test_switch_theme_keeps_data(self, client, user):
        memorial = MemorialFactory(owner=user, description="История")
        other = ThemeFactory(key="other")

        response = client.patch(detail_url(memorial), {"theme": "other"})

        assert response.status_code == 200
        memorial.refresh_from_db()
        assert memorial.theme == other
        assert memorial.description == "История"

    def test_keeps_inactive_current_theme(self, client, user):
        memorial = MemorialFactory(owner=user)
        memorial.theme.is_active = False
        memorial.theme.save()

        response = client.patch(detail_url(memorial), {"first_name": "Пётр"})

        assert response.status_code == 200

    def test_partial_date_update_validated_against_existing(self, client, user):
        memorial = MemorialFactory(owner=user, birth_date="1950-05-17")

        response = client.patch(detail_url(memorial), {"death_date": "1940-01-01"})

        assert response.status_code == 400
        assert "death_date" in response.data

    @pytest.mark.parametrize("method", ["patch", "put"])
    def test_short_code_cannot_be_changed_via_api(self, client, user, method):
        memorial = MemorialFactory(owner=user)
        code = memorial.short_code
        payload = {
            "first_name": "A",
            "last_name": "B",
            "theme": memorial.theme.key,
            "short_code": "CHANGED2",
        }

        response = getattr(client, method)(detail_url(memorial), payload)

        assert response.status_code == 200
        assert response.data["short_code"] == code
        memorial.refresh_from_db()
        assert memorial.short_code == code

    def test_status_cannot_be_changed_via_patch(self, client, user):
        memorial = MemorialFactory(owner=user)

        client.patch(detail_url(memorial), {"status": "published"})

        memorial.refresh_from_db()
        assert memorial.status == Memorial.Status.DRAFT


class TestPublish:
    def test_publish_and_unpublish(self, client, user):
        memorial = MemorialFactory(owner=user)

        response = client.post(detail_url(memorial, "publish/"))
        assert response.status_code == 200
        assert response.data["status"] == "published"
        assert response.data["published_at"] is not None

        response = client.post(detail_url(memorial, "unpublish/"))
        assert response.status_code == 200
        assert response.data["status"] == "draft"


def test_delete(client, user):
    memorial = MemorialFactory(owner=user)

    assert client.delete(detail_url(memorial)).status_code == 204
    assert not Memorial.objects.filter(pk=memorial.pk).exists()


def test_create_with_real_cookie_auth_requires_csrf(csrf_client):
    """Полный путь: login → cookie → POST с CSRF; без CSRF-заголовка — 403."""
    ThemeFactory()
    user = UserFactory()
    csrf_client.post("/api/v1/auth/login/", {"email": user.email, "password": PASSWORD})

    assert csrf_client.post(LIST_URL, {"first_name": "A", "last_name": "B"}).status_code == 201
    csrf_client.credentials()
    assert csrf_client.post(LIST_URL, {"first_name": "A", "last_name": "B"}).status_code == 403
