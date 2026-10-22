from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.memorials.models import Photo


@receiver(post_delete, sender=Photo)
def delete_photo_files(sender, instance: Photo, **kwargs) -> None:
    """Удаляет оригинал и варианты — и при удалении фото, и каскадом со страницей."""
    storage = instance.original.storage
    keys = instance.storage_keys()
    transaction.on_commit(lambda: [storage.delete(key) for key in keys])
