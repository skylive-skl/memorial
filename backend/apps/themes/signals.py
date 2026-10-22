from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.core.revalidation import schedule_revalidation, theme_tag
from apps.themes.models import Theme, ThemeAsset


@receiver(post_save, sender=Theme)
@receiver(post_delete, sender=Theme)
def revalidate_theme(sender, instance: Theme, **kwargs) -> None:
    tags = {theme_tag(instance.key)}
    previous_key = getattr(instance, "_previous_key", None)
    if previous_key and previous_key != instance.key:
        tags.add(theme_tag(previous_key))  # страницы закешированы под старым ключом
    schedule_revalidation(*tags)


@receiver(post_save, sender=ThemeAsset)
@receiver(post_delete, sender=ThemeAsset)
def revalidate_asset_theme(sender, instance: ThemeAsset, **kwargs) -> None:
    schedule_revalidation(theme_tag(instance.theme.key))
