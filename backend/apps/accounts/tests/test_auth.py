import pytest
from django.conf import settings
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.tests.factories import PASSWORD, UserFactory

pytestmark = pytest.mark.django_db

ACCESS = settings.AUTH_COOKIE_ACCESS
REFRESH = settings.AUTH_COOKIE_REFRESH


def login(client: APIClient, email: str, password: str = PASSWORD):
    return client.post("/api/v1/auth/login/", {"email": email, "password": password})


class TestRegister:
    def test_creates_user_and_logs_in(self, csrf_client):
        response = csrf_client.post(
            "/api/v1/auth/register/",
            {"email": "New@Example.com", "password": PASSWORD, "preferred_language": "uz"},
        )

        assert response.status_code == 201
        assert response.data["email"] == "new@example.com"
        assert response.data["preferred_language"] == "uz"
        assert "password" not in response.data
        user = User.objects.get(email="new@example.com")
        assert user.check_password(PASSWORD)
        assert response.cookies[ACCESS].value
        assert response.cookies[REFRESH].value

    def test_default_language_is_ru(self, csrf_client):
        response = csrf_client.post(
            "/api/v1/auth/register/", {"email": "a@example.com", "password": PASSWORD}
        )

        assert response.status_code == 201
        assert response.data["preferred_language"] == "ru"

    def test_duplicate_email_case_insensitive(self, csrf_client):
        UserFactory(email="taken@example.com")

        response = csrf_client.post(
            "/api/v1/auth/register/", {"email": "TAKEN@example.com", "password": PASSWORD}
        )

        assert response.status_code == 400
        assert "email" in response.data

    def test_weak_password_rejected(self, csrf_client):
        response = csrf_client.post(
            "/api/v1/auth/register/", {"email": "a@example.com", "password": "123"}
        )

        assert response.status_code == 400
        assert not User.objects.exists()


class TestLogin:
    def test_sets_httponly_cookies(self, csrf_client):
        user = UserFactory()

        response = login(csrf_client, user.email.upper())

        assert response.status_code == 200
        assert response.data["email"] == user.email
        access, refresh = response.cookies[ACCESS], response.cookies[REFRESH]
        assert access["httponly"] and refresh["httponly"]
        assert access["samesite"] == refresh["samesite"] == "Lax"
        assert access["path"] == "/"
        assert refresh["path"] == settings.AUTH_COOKIE_REFRESH_PATH

    def test_wrong_password(self, csrf_client):
        user = UserFactory()

        response = login(csrf_client, user.email, "wrong-password")

        assert response.status_code == 401
        assert ACCESS not in response.cookies

    def test_inactive_user(self, csrf_client):
        user = UserFactory(is_active=False)

        assert login(csrf_client, user.email).status_code == 401

    def test_stale_access_cookie_does_not_block_login(self, csrf_client):
        user = UserFactory()
        csrf_client.cookies[ACCESS] = "garbage"

        assert login(csrf_client, user.email).status_code == 200


class TestMe:
    def test_returns_current_user(self, csrf_client):
        user = UserFactory()
        login(csrf_client, user.email)

        response = csrf_client.get("/api/v1/auth/me/")

        assert response.status_code == 200
        assert response.data == {
            "id": user.id,
            "email": user.email,
            "preferred_language": "ru",
            "created_at": response.data["created_at"],
        }

    def test_anonymous_gets_401(self, api_client):
        assert api_client.get("/api/v1/auth/me/").status_code == 401

    def test_invalid_access_token_gets_401(self, api_client):
        api_client.cookies[ACCESS] = "garbage"

        assert api_client.get("/api/v1/auth/me/").status_code == 401


class TestRefresh:
    def test_rotates_tokens(self, csrf_client):
        user = UserFactory()
        old_refresh = login(csrf_client, user.email).cookies[REFRESH].value

        response = csrf_client.post("/api/v1/auth/refresh/")

        assert response.status_code == 204
        assert response.cookies[ACCESS].value
        assert response.cookies[REFRESH].value != old_refresh
        assert csrf_client.get("/api/v1/auth/me/").status_code == 200

    def test_old_refresh_token_is_blacklisted(self, csrf_client):
        user = UserFactory()
        old_refresh = login(csrf_client, user.email).cookies[REFRESH].value
        csrf_client.post("/api/v1/auth/refresh/")

        csrf_client.cookies[REFRESH] = old_refresh
        response = csrf_client.post("/api/v1/auth/refresh/")

        assert response.status_code == 401
        assert response.cookies[ACCESS].value == ""

    def test_without_cookie_gets_401(self, csrf_client):
        assert csrf_client.post("/api/v1/auth/refresh/").status_code == 401


class TestLogout:
    def test_clears_cookies_and_blacklists_refresh(self, csrf_client):
        user = UserFactory()
        refresh = login(csrf_client, user.email).cookies[REFRESH].value

        response = csrf_client.post("/api/v1/auth/logout/")

        assert response.status_code == 204
        assert response.cookies[ACCESS].value == ""
        assert response.cookies[REFRESH].value == ""
        csrf_client.cookies[REFRESH] = refresh
        assert csrf_client.post("/api/v1/auth/refresh/").status_code == 401

    def test_anonymous_logout_is_noop(self, csrf_client):
        assert csrf_client.post("/api/v1/auth/logout/").status_code == 204


class TestCsrf:
    @pytest.mark.parametrize("path", ["register", "login", "refresh", "logout"])
    def test_auth_posts_require_csrf_token(self, path):
        client = APIClient(enforce_csrf_checks=True)

        response = client.post(f"/api/v1/auth/{path}/", {"email": "a@example.com"})

        assert response.status_code == 403

    def test_cookie_authenticated_unsafe_request_requires_csrf_token(self, csrf_client):
        # POST на GET-only эндпоинт: аутентификация (и CSRF-проверка) идёт раньше 405.
        user = UserFactory()
        login(csrf_client, user.email)

        assert csrf_client.post("/api/v1/auth/me/").status_code == 405
        csrf_client.credentials()  # убираем X-CSRFToken
        assert csrf_client.post("/api/v1/auth/me/").status_code == 403

    def test_safe_methods_do_not_require_csrf_token(self, csrf_client):
        user = UserFactory()
        login(csrf_client, user.email)
        csrf_client.credentials()

        assert csrf_client.get("/api/v1/auth/me/").status_code == 200
