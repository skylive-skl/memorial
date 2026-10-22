import contextlib

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import update_last_login
from django.middleware.csrf import get_token
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.authentication import enforce_csrf
from apps.accounts.cookies import clear_auth_cookies, set_auth_cookies
from apps.accounts.models import User
from apps.accounts.serializers import LoginSerializer, RegisterSerializer, UserSerializer


class PublicAuthView(APIView):
    """Эндпоинты входа: без аутентификации (протухший access-cookie не должен мешать
    войти), но с обязательной CSRF-проверкой."""

    authentication_classes = ()
    permission_classes = (AllowAny,)

    def initial(self, request: Request, *args, **kwargs) -> None:
        super().initial(request, *args, **kwargs)
        enforce_csrf(request)


def _login_response(user: User, status_code: int) -> Response:
    refresh = RefreshToken.for_user(user)
    update_last_login(None, user)
    response = Response(UserSerializer(user).data, status=status_code)
    set_auth_cookies(response, access=str(refresh.access_token), refresh=str(refresh))
    return response


class CsrfView(PublicAuthView):
    @extend_schema(request=None, responses={204: None})
    def get(self, request: Request) -> Response:
        """Выставляет cookie `csrftoken`; фронт шлёт её значение в заголовке `X-CSRFToken`."""
        get_token(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RegisterView(PublicAuthView):
    @extend_schema(request=RegisterSerializer, responses={201: UserSerializer})
    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return _login_response(user, status.HTTP_201_CREATED)


class LoginView(PublicAuthView):
    @extend_schema(request=LoginSerializer, responses={200: UserSerializer})
    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            # Ответ формируем сами: без authentication_classes DRF превратил бы
            # AuthenticationFailed в 403.
            return Response(
                {"detail": "Invalid email or password.", "code": "invalid_credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return _login_response(user, status.HTTP_200_OK)


class RefreshView(PublicAuthView):
    @extend_schema(request=None, responses={204: None})
    def post(self, request: Request) -> Response:
        raw = request.COOKIES.get(settings.AUTH_COOKIE_REFRESH)
        serializer = TokenRefreshSerializer(data={"refresh": raw or ""})
        try:
            serializer.is_valid(raise_exception=True)
        except (TokenError, exceptions.ValidationError, exceptions.AuthenticationFailed):
            response = Response(
                {"detail": "Refresh token is invalid or expired."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            clear_auth_cookies(response)
            return response
        response = Response(status=status.HTTP_204_NO_CONTENT)
        set_auth_cookies(
            response,
            access=serializer.validated_data["access"],
            refresh=serializer.validated_data.get("refresh"),
        )
        return response


class LogoutView(PublicAuthView):
    @extend_schema(request=None, responses={204: None})
    def post(self, request: Request) -> Response:
        raw = request.COOKIES.get(settings.AUTH_COOKIE_REFRESH)
        if raw:
            with contextlib.suppress(TokenError):
                RefreshToken(raw).blacklist()
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_auth_cookies(response)
        return response


class MeView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses={200: UserSerializer})
    def get(self, request: Request) -> Response:
        return Response(UserSerializer(request.user).data)
