# CLAUDE.md — Сервис мемориальных страниц

## О проекте

Веб-сервис, где пользователь создаёт страницу памяти для умершего родственника:
ФИО, даты рождения и смерти, фотографии, текстовое описание. Пользователь выбирает
оформление (тему) из каталога и может в любой момент переключить его.
Опубликованная страница доступна по короткой ссылке и через QR-код, который
наносят на памятник.

Подробный план работ: `docs/PLAN.md`. Работай строго по нему.

## Зафиксированные решения (не менять без согласования)

- **Стек:** Next.js (App Router, TypeScript) + Django + Django REST Framework + PostgreSQL.
- **Фоновые задачи:** Celery + Redis (обработка фото, генерация QR).
- **Файлы:** S3-совместимое хранилище (локально SeaweedFS — образы MinIO больше не публикуются), через `django-storages`.
- **Языки интерфейса:** ru, uz (латиница), en. Фронт — `next-intl`, бэк — `django-modeltranslation` для переводимых полей тем.
- **Страницы только для чтения**: никаких комментариев, свечей и т. п. в MVP.
- **Доступ по ссылке:** страница не индексируется (`noindex`), URL содержит случайный код, а не имя человека.
- **Монетизации в MVP нет.**
- **Авторизация в MVP:** email + пароль, JWT (`djangorestframework-simplejwt`) в httpOnly cookies.
- **Один origin:** браузер ходит только на Next.js; Next проксирует `/api/v1/*` (и Swagger) на Django через `rewrites`. Cookie выставляются на домен фронта, CORS для браузера не нужен. `/api/revalidate` — собственный route handler Next.
- **Медиа:** фото и ассеты тем отдаются по прямым публичным URL бакета (public-read). В базе хранятся только **ключи файлов**, URL собираются при отдаче из API (в т. ч. `Photo.variants`).
- **Недоступная публичная страница:** API отдаёт 404 и для черновика, и для несуществующего кода (не раскрываем, существует ли страница); фронт на `/m/[code]` показывает дружелюбную страницу «Страница недоступна» с HTTP 404.
- **CI:** GitHub Actions. Репозиторий: `https://github.com/skylive-skl/memorial.git`.
- **Лимит фото:** 50 на страницу.
- **Редактор:** автосохранение с задержкой (debounce), без кнопки «Сохранить».
- **Прод-хостинг:** не определён — задачу 4.4 не начинать без согласования.

## Архитектура тем — главный принцип

Тема = **layout** + **оформление**.

- **Layout** — React-компонент в коде фронтенда (`frontend/src/themes/layouts/*`). Их мало (2 в MVP), они версионируются с кодом.
- **Оформление** — JSON (`Theme.tokens`) в базе: какой layout, его опции, цвета, шрифты, фон, ассеты.
- Данные страницы (`Memorial`) **никогда** не зависят от темы. Смена темы = смена `Memorial.theme`.
- Новая тема добавляется через Django Admin **без деплоя**. Новый layout — через код.
- **Запрещено** хранить в базе произвольный HTML/CSS/JS тем.
- **Запрещено** хардкодить цвета, шрифты и фоны внутри layout-компонентов: всё визуальное берётся из CSS-переменных, которые выставляются из `tokens`.
- `tokens` валидируются JSON Schema на бэке (`jsonschema`) и zod-схемой на фронте. Схема — в `docs/PLAN.md`, раздел «Формат темы».
- Неизвестный `layout` на фронте → fallback на `classic`, страница не должна падать.

## Критичные инварианты

1. `Memorial.short_code` генерируется один раз и **никогда не меняется** (QR выгравирован на камне). Изменение запрещено на уровне модели (`save()` и сериализаторов) и покрыто тестом.
2. Публичный эндпоинт отдаёт только опубликованные страницы. Черновик → 404.
3. Оригиналы фото сохраняются всегда; варианты размеров генерируются отдельно.
4. Даты хранятся вместе с точностью (`day` / `month` / `year`) и отображаются в соответствии с ней.

## Структура репозитория

```
/
├── CLAUDE.md
├── docs/PLAN.md
├── docker-compose.yml          # postgres, redis, s3 (SeaweedFS), backend, worker, frontend
├── .env.example
├── backend/
│   ├── config/                 # settings (base/dev/prod), urls, celery
│   ├── apps/
│   │   ├── accounts/
│   │   ├── memorials/
│   │   └── themes/
│   ├── requirements/           # base.txt, dev.txt
│   └── pytest.ini
└── frontend/
    ├── src/app/                # [locale]/... кабинет, m/[code] публичная
    ├── src/themes/             # registry, layouts, tokens → CSS vars, zod-схема
    ├── src/lib/api/            # типизированный клиент API
    └── messages/               # ru.json, uz.json, en.json
```

## Правила работы

- Выполняй задачи из `docs/PLAN.md` **по одной, по порядку**. После завершения задачи отметь её `[x]` и кратко опиши, что сделано.
- Задача считается готовой, только если выполнены все её критерии приёмки и проходят тесты и линтеры.
- Если задача требует решения, которого нет в этом файле или в плане, — **остановись и спроси**, не придумывай архитектуру сам.
- Маленькие осмысленные коммиты, сообщения на английском в формате Conventional Commits (`feat(memorials): ...`).
- Бэкенд: Python 3.12+, `ruff` (lint + format), `pytest` + `pytest-django`, `factory_boy`. Типизация — где разумно.
- Фронтенд: TypeScript strict, ESLint, Prettier, Vitest для логики (утилиты дат, токены тем, реестр layout'ов).
- Никаких секретов в коде: всё через `.env`, пример в `.env.example`.
- Тексты интерфейса — только через файлы переводов, никаких строк в JSX.

## Команды

Первый запуск: `cp .env.example .env`. Всё запускается в Docker; локально нужны только Docker и (для фронта вне контейнера) Node 22.

```bash
docker compose up -d                 # всё: postgres, redis, s3, backend, worker, frontend
docker compose up -d --build backend worker   # после изменения requirements/
docker compose ps                    # статусы и healthchecks
docker compose logs -f backend       # логи сервиса

# backend (в контейнере)
docker compose exec backend python manage.py makemigrations
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py createsuperuser
docker compose exec backend pytest                 # тесты
docker compose exec backend ruff check .           # линт
docker compose exec backend ruff format .          # форматирование

# frontend (из frontend/, локально)
npm install
npm run lint && npm run format:check && npm run typecheck && npm test
npm run build
```

Адреса: фронт http://localhost:3000, API и Swagger через прокси фронта (`/api/v1/`, `/api/docs/`),
Django Admin http://localhost:8000/admin/, медиа http://localhost:8333/memorial-media/.

CI (GitHub Actions, `.github/workflows/ci.yml`) запускает те же проверки: ruff, проверку
несозданных миграций (`makemigrations --check`), pytest; ESLint, Prettier, typecheck, Vitest и `next build`.
