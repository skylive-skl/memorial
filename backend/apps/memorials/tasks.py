import logging

from celery import shared_task
from django.core.files.base import ContentFile

from apps.memorials.images import make_variants
from apps.memorials.models import Photo

logger = logging.getLogger(__name__)


@shared_task
def process_photo(photo_id: int) -> None:
    """Исправляет ориентацию, убирает EXIF и создаёт варианты thumb/medium/large."""
    photo = Photo.objects.filter(pk=photo_id).first()
    if photo is None:
        return  # удалено до обработки
    storage = photo.original.storage
    try:
        with photo.original.open("rb") as original:
            width, height, variants = make_variants(original)
        keys = {}
        for name, content in variants.items():
            key = photo.variant_key(name)
            storage.delete(key)  # повторная обработка перезаписывает варианты
            keys[name] = storage.save(key, ContentFile(content))
    except Exception:
        logger.exception("Photo %s processing failed", photo_id)
        Photo.objects.filter(pk=photo_id).update(processing_status=Photo.ProcessingStatus.FAILED)
        return

    # update(), а не save(): не затираем подпись/порядок, изменённые во время обработки.
    updated = Photo.objects.filter(pk=photo_id).update(
        variants=keys, width=width, height=height, processing_status=Photo.ProcessingStatus.READY
    )
    if not updated:  # фото удалили, пока шла обработка
        for key in keys.values():
            storage.delete(key)
