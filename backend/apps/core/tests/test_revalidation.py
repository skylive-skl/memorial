import contextlib
import json
import urllib.error
from unittest import mock

import pytest
from django.db import transaction
from rest_framework.test import APIClient

from apps.core import revalidation
from apps.core.revalidation import RetryableRevalidationError, send_revalidation
from apps.core.tasks import revalidate_tags
from apps.memorials.models import Photo
from apps.memorials.tasks import process_photo
from apps.memorials.tests.factories import MemorialFactory
from apps.memorials.tests.test_photos import make_photo
from apps.themes.models import ThemeAsset
from apps.themes.tests.factories import ThemeAssetFactory, ThemeFactory


def queued_tags(delay: mock.Mock) -> list[list[str]]:
    return [call.args[0] for call in delay.call_args_list]


@pytest.mark.django_db
class TestSignals:
    @pytest.fixture
    def commit(self, django_capture_on_commit_callbacks):
        """«Новая транзакция с коммитом». Теги, накопленные при подготовке теста
        (в тестовой транзакции, которая никогда не коммитится), отбрасываются."""

        @contextlib.contextmanager
        def committed():
            revalidation._local.tags = set()
            with django_capture_on_commit_callbacks(execute=True):
                yield

        return committed

    def test_memorial_save(self, commit, revalidation_queue):
        memorial = MemorialFactory()
        revalidation_queue.reset_mock()

        with commit():
            memorial.description = "x"
            memorial.save()

        assert queued_tags(revalidation_queue) == [[f"memorial:{memorial.short_code}"]]

    @pytest.mark.parametrize("action", ["publish", "unpublish", "delete"])
    def test_memorial_publish_unpublish_delete(self, commit, revalidation_queue, action):
        memorial = MemorialFactory()
        revalidation_queue.reset_mock()

        with commit():
            getattr(memorial, action)()

        assert [f"memorial:{memorial.short_code}"] in queued_tags(revalidation_queue)

    def test_one_task_per_transaction(self, commit, revalidation_queue):
        memorial = MemorialFactory()
        theme = ThemeFactory()
        revalidation_queue.reset_mock()

        with commit(), transaction.atomic():
            for _ in range(3):
                memorial.save()
            make_photo(memorial)
            theme.save()

        assert queued_tags(revalidation_queue) == [
            sorted([f"memorial:{memorial.short_code}", f"theme:{theme.key}"])
        ]

    def test_rolled_back_transaction_queues_nothing(self, commit, revalidation_queue):
        memorial = MemorialFactory()
        revalidation_queue.reset_mock()

        with commit(), pytest.raises(RuntimeError), transaction.atomic():
            memorial.save()
            raise RuntimeError

        revalidation_queue.assert_not_called()

    def test_photo_save_and_delete(self, commit, revalidation_queue):
        memorial = MemorialFactory()
        tag = [f"memorial:{memorial.short_code}"]

        with commit():
            photo = make_photo(memorial)
        assert queued_tags(revalidation_queue)[-1] == tag

        revalidation_queue.reset_mock()
        with commit():
            photo.delete()
        assert queued_tags(revalidation_queue) == [tag]

    def test_photo_processing_done(self, commit, revalidation_queue):
        photo = make_photo(MemorialFactory())
        revalidation_queue.reset_mock()

        with commit():
            process_photo(photo.pk)

        assert queued_tags(revalidation_queue) == [[f"memorial:{photo.memorial.short_code}"]]
        assert Photo.objects.get(pk=photo.pk).processing_status == "ready"

    def test_photo_reorder(self, commit, revalidation_queue):
        memorial = MemorialFactory()
        photos = [make_photo(memorial, order=i) for i in range(2)]
        client = APIClient()
        client.force_authenticate(memorial.owner)
        revalidation_queue.reset_mock()

        with commit():
            response = client.patch(
                f"/api/v1/memorials/{memorial.id}/photos/reorder/",
                [photos[1].pk, photos[0].pk],
                format="json",
            )

        assert response.status_code == 200
        assert queued_tags(revalidation_queue) == [[f"memorial:{memorial.short_code}"]]

    def test_theme_save_and_delete(self, commit, revalidation_queue):
        theme = ThemeFactory(key="emerald")
        revalidation_queue.reset_mock()

        with commit():
            theme.tokens["radius"] = "0"
            theme.save()
        assert queued_tags(revalidation_queue) == [["theme:emerald"]]

        revalidation_queue.reset_mock()
        with commit():
            theme.delete()
        assert queued_tags(revalidation_queue) == [["theme:emerald"]]

    def test_theme_key_change_revalidates_both_keys(self, commit, revalidation_queue):
        theme = ThemeFactory(key="old-key")
        revalidation_queue.reset_mock()

        with commit():
            theme.key = "new-key"
            theme.save()

        assert queued_tags(revalidation_queue) == [["theme:new-key", "theme:old-key"]]

    def test_theme_asset_save_and_delete(self, commit, revalidation_queue):
        theme = ThemeFactory(key="emerald")
        revalidation_queue.reset_mock()

        with commit():
            asset = ThemeAssetFactory(theme=theme)
        assert queued_tags(revalidation_queue) == [["theme:emerald"]]

        revalidation_queue.reset_mock()
        with commit():
            ThemeAsset.objects.get(pk=asset.pk).delete()
        assert queued_tags(revalidation_queue) == [["theme:emerald"]]


class TestSendRevalidation:
    @pytest.fixture(autouse=True)
    def frontend(self, settings):
        settings.FRONTEND_INTERNAL_URL = "http://frontend:3000"
        settings.REVALIDATE_SECRET = "s3cret"

    def test_request(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            send_revalidation(["memorial:abc", "theme:x"])

        request = urlopen.call_args.args[0]
        assert request.full_url == "http://frontend:3000/api/revalidate"
        assert request.get_method() == "POST"
        assert request.get_header("X-revalidate-secret") == "s3cret"
        assert request.get_header("Content-type") == "application/json"
        assert json.loads(request.data) == {"tags": ["memorial:abc", "theme:x"]}

    @pytest.mark.parametrize(
        "error",
        [
            urllib.error.HTTPError("u", 502, "Bad Gateway", None, None),
            urllib.error.URLError("connection refused"),
            TimeoutError(),
        ],
    )
    def test_retryable_errors(self, error):
        with (
            mock.patch("urllib.request.urlopen", side_effect=error),
            pytest.raises(RetryableRevalidationError),
        ):
            send_revalidation(["memorial:abc"])

    def test_client_error_is_logged_not_retried(self, caplog):
        error = urllib.error.HTTPError("u", 401, "Unauthorized", None, None)

        with mock.patch("urllib.request.urlopen", side_effect=error):
            send_revalidation(["memorial:abc"])

        assert "HTTP 401" in caplog.text

    def test_task_retries_retryable_errors(self):
        assert RetryableRevalidationError in revalidate_tags.autoretry_for
        assert revalidate_tags.max_retries == 8
