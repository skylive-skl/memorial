"""On-demand ревалидация кеша публичных страниц на фронте.

Контракт (route handler фронта, задача 2.7):
    POST {FRONTEND_INTERNAL_URL}/api/revalidate
    X-Revalidate-Secret: {REVALIDATE_SECRET}
    {"tags": ["memorial:<short_code>", "theme:<key>", ...]}
"""

import json
import logging
import threading
import urllib.error
import urllib.request

from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)

_local = threading.local()


def memorial_tag(short_code: str) -> str:
    return f"memorial:{short_code}"


def theme_tag(key: str) -> str:
    return f"theme:{key}"


def schedule_revalidation(*tags: str) -> None:
    """Копит теги и после коммита ставит одну задачу на все накопленные.

    Вне транзакции срабатывает сразу. Если транзакция откатилась, её теги уйдут
    со следующим коммитом — лишняя ревалидация безвредна.
    """
    _local.tags = getattr(_local, "tags", set()) | set(tags)
    transaction.on_commit(_flush)


def _flush() -> None:
    tags = getattr(_local, "tags", set())
    _local.tags = set()
    if tags:
        from apps.core.tasks import revalidate_tags

        revalidate_tags.delay(sorted(tags))


class RetryableRevalidationError(Exception):
    """Фронт недоступен или ответил 5xx — стоит повторить."""


def send_revalidation(tags: list[str]) -> None:
    request = urllib.request.Request(
        f"{settings.FRONTEND_INTERNAL_URL}/api/revalidate",
        data=json.dumps({"tags": tags}).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Revalidate-Secret": settings.REVALIDATE_SECRET,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10):
            pass
    except urllib.error.HTTPError as exc:
        if exc.code >= 500:
            raise RetryableRevalidationError(f"Frontend responded {exc.code}") from exc
        # 4xx (например, неверный секрет) повтором не исправить.
        logger.error("Revalidation of %s rejected by frontend: HTTP %s", tags, exc.code)
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise RetryableRevalidationError(str(exc)) from exc
