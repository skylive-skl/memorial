import io
from unittest import mock

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.memorials.models import Memorial, Photo
from apps.memorials.tasks import process_photo
from apps.memorials.tests.factories import MemorialFactory
from apps.memorials.tests.images import image_bytes, jpeg_bytes, upload

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return UserFactory()


@pytest.fixture
def client(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def memorial(user) -> Memorial:
    return MemorialFactory(owner=user)


def photos_url(memorial: Memorial, suffix: str = "") -> str:
    return f"/api/v1/memorials/{memorial.id}/photos/{suffix}"


def make_photo(memorial: Memorial, **kwargs) -> Photo:
    photo = Photo(memorial=memorial, **kwargs)
    photo.original.save("p.jpg", ContentFile(jpeg_bytes()))
    return photo


def post_photo(client, memorial, name="photo.jpg", content=None, **extra):
    return client.post(
        photos_url(memorial),
        {"file": upload(name, content or jpeg_bytes()), **extra},
        format="multipart",
    )


class TestUpload:
    def test_stores_original_and_enqueues_processing(
        self, client, memorial, django_capture_on_commit_callbacks
    ):
        with (
            mock.patch("apps.memorials.views.process_photo.delay") as delay,
            django_capture_on_commit_callbacks(execute=True),
        ):
            response = post_photo(client, memorial, caption="Бабушка, 1975")

        assert response.status_code == 201, response.data
        photo = Photo.objects.get(pk=response.data["id"])
        assert photo.caption == "Бабушка, 1975"
        assert photo.processing_status == "pending"
        assert photo.original.name == f"photos/{photo.folder}/original.jpg"
        assert default_storage.exists(photo.original.name)
        delay.assert_called_once_with(photo.pk)

    def test_original_kept_byte_for_byte(self, client, memorial):
        content = jpeg_bytes(gps=True)

        response = post_photo(client, memorial, content=content)

        photo = Photo.objects.get(pk=response.data["id"])
        with photo.original.open("rb") as f:
            assert f.read() == content

    def test_storage_folder_is_random(self, client, memorial):
        first = post_photo(client, memorial).data["id"]
        second = post_photo(client, memorial).data["id"]

        folders = set(Photo.objects.filter(pk__in=[first, second]).values_list("folder", flat=True))
        assert len(folders) == 2
        assert all(len(f) == 32 for f in folders)

    @pytest.mark.parametrize(
        ("name", "fmt", "content_type"),
        [
            ("a.png", "PNG", "image/png"),
            ("a.webp", "WEBP", "image/webp"),
            ("a.heic", "HEIF", "image/heic"),
        ],
    )
    def test_supported_formats(self, client, memorial, name, fmt, content_type):
        response = client.post(
            photos_url(memorial),
            {"file": upload(name, image_bytes(fmt), content_type)},
            format="multipart",
        )

        assert response.status_code == 201, response.data

    def test_unsupported_format(self, client, memorial):
        response = post_photo(client, memorial, "a.gif", image_bytes("GIF"))

        assert response.status_code == 400
        assert "file" in response.data

    def test_not_an_image_with_image_extension(self, client, memorial):
        response = post_photo(client, memorial, "a.jpg", b"<html>nope</html>")

        assert response.status_code == 400
        assert not Photo.objects.exists()

    def test_too_large(self, client, memorial, settings):
        settings.PHOTO_MAX_UPLOAD_BYTES = 1000

        response = post_photo(client, memorial, content=jpeg_bytes((800, 800)))

        assert response.status_code == 400
        assert "too large" in str(response.data["file"])

    def test_limit_per_memorial(self, client, memorial, settings):
        settings.PHOTO_MAX_PER_MEMORIAL = 2
        assert post_photo(client, memorial).status_code == 201
        assert post_photo(client, memorial).status_code == 201

        response = post_photo(client, memorial)

        assert response.status_code == 400
        assert memorial.photos.count() == 2

    def test_first_photo_becomes_cover_and_order_grows(self, client, memorial):
        ids = [post_photo(client, memorial).data["id"] for _ in range(3)]

        photos = list(Photo.objects.filter(pk__in=ids).order_by("id"))
        assert [p.is_cover for p in photos] == [True, False, False]
        assert [p.order for p in photos] == [0, 1, 2]

    def test_foreign_memorial(self, client):
        assert post_photo(client, MemorialFactory()).status_code == 404

    def test_anonymous(self, memorial):
        assert post_photo(APIClient(), memorial).status_code == 401

    def test_listed_in_memorial(self, client, memorial):
        post_photo(client, memorial)

        response = client.get(f"/api/v1/memorials/{memorial.id}/")

        assert len(response.data["photos"]) == 1
        assert client.get(photos_url(memorial)).data[0]["id"] == response.data["photos"][0]["id"]


class TestProcessing:
    def test_creates_variants(self, memorial):
        photo = make_photo(memorial)

        process_photo(photo.pk)

        photo.refresh_from_db()
        assert photo.processing_status == "ready"
        assert (photo.width, photo.height) == (400, 200)
        assert set(photo.variants) == {"thumb", "medium", "large"}
        for name, key in photo.variants.items():
            assert key == f"photos/{photo.folder}/{name}.webp"
            assert default_storage.exists(key)

    def test_variant_urls_in_api(self, client, memorial):
        photo = make_photo(memorial)
        process_photo(photo.pk)

        data = client.get(photos_url(memorial)).data[0]

        assert data["variants"]["thumb"].endswith(f"photos/{photo.folder}/thumb.webp")
        assert data["variants"]["thumb"].startswith("http")

    def test_reprocessing_overwrites_variants(self, memorial):
        photo = make_photo(memorial)
        process_photo(photo.pk)

        process_photo(photo.pk)

        photo.refresh_from_db()
        assert photo.variants["thumb"] == f"photos/{photo.folder}/thumb.webp"

    def test_broken_original_marks_failed(self, memorial):
        photo = Photo(memorial=memorial)
        photo.original.save("p.jpg", ContentFile(b"broken"))

        process_photo(photo.pk)

        photo.refresh_from_db()
        assert photo.processing_status == "failed"
        assert photo.variants == {}

    def test_deleted_photo_is_ignored(self):
        process_photo(999_999)

    def test_keeps_caption_changed_during_processing(self, memorial):
        photo = make_photo(memorial)
        Photo.objects.filter(pk=photo.pk).update(caption="новая")

        process_photo(photo.pk)

        photo.refresh_from_db()
        assert photo.caption == "новая"


class TestCover:
    def test_set_cover_unsets_previous(self, client, memorial):
        first = make_photo(memorial, is_cover=True, order=0)
        second = make_photo(memorial, order=1)

        response = client.patch(photos_url(memorial, f"{second.pk}/"), {"is_cover": True})

        assert response.status_code == 200
        first.refresh_from_db()
        second.refresh_from_db()
        assert (first.is_cover, second.is_cover) == (False, True)

    def test_db_allows_only_one_cover(self, memorial):
        make_photo(memorial, is_cover=True)

        with pytest.raises(IntegrityError), transaction.atomic():
            make_photo(memorial, is_cover=True)

    def test_deleting_cover_promotes_next(self, client, memorial):
        cover = make_photo(memorial, is_cover=True, order=0)
        next_photo = make_photo(memorial, order=1)

        assert client.delete(photos_url(memorial, f"{cover.pk}/")).status_code == 204

        next_photo.refresh_from_db()
        assert next_photo.is_cover


class TestEdit:
    def test_caption(self, client, memorial):
        photo = make_photo(memorial)

        response = client.patch(photos_url(memorial, f"{photo.pk}/"), {"caption": "Свадьба"})

        assert response.status_code == 200
        photo.refresh_from_db()
        assert photo.caption == "Свадьба"

    def test_read_only_fields(self, client, memorial):
        photo = make_photo(memorial, order=0)

        client.patch(
            photos_url(memorial, f"{photo.pk}/"), {"order": 7, "processing_status": "ready"}
        )

        photo.refresh_from_db()
        assert (photo.order, photo.processing_status) == (0, "pending")

    def test_foreign_photo(self, client):
        foreign = make_photo(MemorialFactory())

        for method in ("patch", "delete"):
            response = getattr(client, method)(photos_url(foreign.memorial, f"{foreign.pk}/"))
            assert response.status_code == 404
        assert Photo.objects.filter(pk=foreign.pk).exists()

    def test_photo_of_other_own_memorial_via_wrong_url(self, client, user, memorial):
        photo = make_photo(MemorialFactory(owner=user))

        response = client.patch(photos_url(memorial, f"{photo.pk}/"), {"caption": "x"})

        assert response.status_code == 404


class TestReorder:
    def test_reorder(self, client, memorial):
        a, b, c = (make_photo(memorial, order=i) for i in range(3))

        response = client.patch(photos_url(memorial, "reorder/"), [c.pk, a.pk, b.pk], format="json")

        assert response.status_code == 200
        assert [p["id"] for p in response.data] == [c.pk, a.pk, b.pk]
        assert list(memorial.photos.values_list("pk", flat=True)) == [c.pk, a.pk, b.pk]

    @pytest.mark.parametrize("payload", ["missing", "duplicate", "foreign", "not-a-list"])
    def test_invalid_payload(self, client, memorial, payload):
        a, b = make_photo(memorial, order=0), make_photo(memorial, order=1)
        foreign = make_photo(MemorialFactory())
        body = {
            "missing": [a.pk],
            "duplicate": [a.pk, a.pk, b.pk],
            "foreign": [a.pk, b.pk, foreign.pk],
            "not-a-list": {"ids": [a.pk, b.pk]},
        }[payload]

        response = client.patch(photos_url(memorial, "reorder/"), body, format="json")

        assert response.status_code == 400
        assert list(memorial.photos.values_list("pk", flat=True)) == [a.pk, b.pk]


class TestDeleteFiles:
    def test_photo_delete_removes_files(self, client, memorial, django_capture_on_commit_callbacks):
        photo = make_photo(memorial)
        process_photo(photo.pk)
        photo.refresh_from_db()
        keys = photo.storage_keys()
        assert len(keys) == 4 and all(default_storage.exists(k) for k in keys)

        with django_capture_on_commit_callbacks(execute=True):
            response = client.delete(photos_url(memorial, f"{photo.pk}/"))

        assert response.status_code == 204
        assert not any(default_storage.exists(k) for k in keys)

    def test_memorial_delete_removes_photo_files(
        self, client, memorial, django_capture_on_commit_callbacks
    ):
        photos = [make_photo(memorial) for _ in range(2)]
        keys = [k for p in photos for k in p.storage_keys()]

        with django_capture_on_commit_callbacks(execute=True):
            assert client.delete(f"/api/v1/memorials/{memorial.id}/").status_code == 204

        assert not Photo.objects.exists()
        assert not any(default_storage.exists(k) for k in keys)

    def test_files_kept_if_transaction_rolls_back(self, memorial):
        photo = make_photo(memorial)

        with pytest.raises(RuntimeError), transaction.atomic():
            photo.delete()
            raise RuntimeError

        assert default_storage.exists(photo.original.name)


def test_variant_is_valid_webp(memorial):
    photo = make_photo(memorial)
    process_photo(photo.pk)
    photo.refresh_from_db()

    with default_storage.open(photo.variants["medium"]) as f:
        assert Image.open(io.BytesIO(f.read())).format == "WEBP"
