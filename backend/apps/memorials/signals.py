from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.core.revalidation import memorial_tag, schedule_revalidation
from apps.memorials.models import Memorial, Photo


@receiver(post_save, sender=Memorial)
@receiver(post_delete, sender=Memorial)
def revalidate_memorial(sender, instance: Memorial, **kwargs) -> None:
    schedule_revalidation(memorial_tag(instance.short_code))


@receiver(post_save, sender=Photo)
def revalidate_photo_memorial(sender, instance: Photo, **kwargs) -> None:
    schedule_revalidation(memorial_tag(instance.memorial.short_code))


@receiver(post_delete, sender=Photo)
def delete_photo_files(sender, instance: Photo, **kwargs) -> None:
    """Удаляет оригинал и варианты — и при удалении фото, и каскадом со страницей."""
    storage = instance.original.storage
    keys = instance.storage_keys()
    transaction.on_commit(lambda: [storage.delete(key) for key in keys])
    schedule_revalidation(memorial_tag(instance.memorial.short_code))
