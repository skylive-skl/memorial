from unittest import mock

import pytest
from rest_framework.test import APIClient

from apps.core import revalidation


@pytest.fixture(autouse=True)
def in_memory_storage(request, settings):
    """Файлы в тестах — в памяти (в CI нет S3). URL собираются как в проде.

    Тесты, проверяющие саму настройку S3, помечаются `@pytest.mark.real_storage`.
    """
    if request.node.get_closest_marker("real_storage"):
        return
    settings.STORAGES = {
        **settings.STORAGES,
        "default": {
            "BACKEND": "django.core.files.storage.InMemoryStorage",
            "OPTIONS": {"base_url": f"{settings.MEDIA_PUBLIC_BASE_URL}/"},
        },
    }


@pytest.fixture(autouse=True)
def revalidation_queue():
    """Задачи ревалидации не уходят в брокер (в CI его нет); тесты проверяют вызовы мока."""
    revalidation._local.tags = set()
    with mock.patch("apps.core.tasks.revalidate_tags.delay") as delay:
        yield delay


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def csrf_client() -> APIClient:
    """Клиент с включённой CSRF-проверкой и уже полученной cookie `csrftoken`."""
    client = APIClient(enforce_csrf_checks=True)
    client.get("/api/v1/auth/csrf/")
    client.credentials(HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
    return client
