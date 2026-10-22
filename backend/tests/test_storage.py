import pytest
from django.core.files.storage import default_storage
from storages.backends.s3 import S3Storage


@pytest.mark.real_storage
def test_default_storage_is_s3_with_public_urls(settings):
    url = default_storage.url("photos/abc/original.jpg")

    assert isinstance(default_storage._wrapped, S3Storage)
    assert url == f"{settings.MEDIA_PUBLIC_BASE_URL}/photos/abc/original.jpg"
