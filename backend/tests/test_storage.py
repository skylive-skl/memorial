from django.core.files.storage import default_storage


def test_media_url_built_from_public_base_url(settings):
    url = default_storage.url("photos/abc/original.jpg")

    assert url == f"{settings.MEDIA_PUBLIC_BASE_URL}/photos/abc/original.jpg"
