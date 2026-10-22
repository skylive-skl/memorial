import pytest


@pytest.mark.django_db
def test_health_ok(client):
    response = client.get("/api/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_schema_available(client):
    response = client.get("/api/schema/")

    assert response.status_code == 200


def test_swagger_ui_available(client):
    response = client.get("/api/docs/")

    assert response.status_code == 200
