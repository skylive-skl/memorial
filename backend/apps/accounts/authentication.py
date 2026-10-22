from django.conf import settings
from django.middleware.csrf import CsrfViewMiddleware
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework import exceptions
from rest_framework.request import Request
from rest_framework_simplejwt.authentication import JWTAuthentication


class _CSRFCheck(CsrfViewMiddleware):
    def _reject(self, request, reason):
        return reason


def enforce_csrf(request: Request) -> None:
    """CSRF-проверка (double submit: cookie `csrftoken` + заголовок `X-CSRFToken`).

    Нужна для всех изменяющих запросов, т. к. браузер сам прикладывает auth-cookie.
    Безопасные методы (GET, HEAD, OPTIONS) не проверяются.
    """
    check = _CSRFCheck(lambda _request: None)
    check.process_request(request)
    reason = check.process_view(request, None, (), {})
    if reason:
        raise exceptions.PermissionDenied(f"CSRF Failed: {reason}")


class JWTCookieAuthentication(JWTAuthentication):
    """JWT access-токен из httpOnly cookie вместо заголовка Authorization."""

    def authenticate(self, request: Request):
        raw_token = request.COOKIES.get(settings.AUTH_COOKIE_ACCESS)
        if raw_token is None:
            return None
        validated_token = self.get_validated_token(raw_token.encode())
        enforce_csrf(request)
        return self.get_user(validated_token), validated_token


class JWTCookieAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.accounts.authentication.JWTCookieAuthentication"
    name = "cookieAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "cookie", "name": settings.AUTH_COOKIE_ACCESS}
