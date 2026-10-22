from celery import shared_task

from apps.core.revalidation import RetryableRevalidationError, send_revalidation


@shared_task(
    autoretry_for=(RetryableRevalidationError,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=8,
)
def revalidate_tags(tags: list[str]) -> None:
    send_revalidation(tags)
