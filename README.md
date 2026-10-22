# Memorial

Сервис мемориальных страниц: пользователь создаёт страницу памяти (ФИО, даты, фото,
описание), выбирает оформление из каталога тем и публикует её. Опубликованная страница
доступна по короткой ссылке `/m/{code}` и через QR-код.

- Контекст и правила проекта: [CLAUDE.md](CLAUDE.md)
- План работ: [docs/PLAN.md](docs/PLAN.md)

## Стек

- **Backend:** Django + Django REST Framework, PostgreSQL, Celery + Redis
- **Frontend:** Next.js (App Router, TypeScript), `next-intl` (ru / uz / en)
- **Файлы:** S3-совместимое хранилище (локально MinIO)

Браузер обращается только к Next.js; запросы `/api/v1/*` Next проксирует на Django.

## Структура

```
backend/     Django-проект (config/, apps/accounts, apps/memorials, apps/themes)
frontend/    Next.js-приложение (src/app, src/themes, src/lib/api, messages/)
docs/        План и документация
```

## Запуск локально

Требования: Docker и Docker Compose v2.

```bash
cp .env.example .env
docker compose up -d
```

После запуска:

| Сервис | Адрес |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:3000/api/v1/ (через прокси Next) |
| Swagger | http://localhost:3000/api/docs/ |
| Django Admin | http://localhost:8000/admin/ |
| MinIO Console | http://localhost:9001 |

> Сервисы появляются по мере выполнения этапа 0 (`docker-compose.yml` — задача 0.2,
> Django — 0.3, Next.js — 0.4). Команды для тестов и линтеров будут добавлены в
> раздел «Команды» `CLAUDE.md` (задача 0.6).
