# План разработки MVP — сервис мемориальных страниц

Контекст и правила — в `CLAUDE.md`. Задачи выполняются строго по порядку.
Каждая задача — примерно одна рабочая сессия. Отмечай `[x]` по завершении.

---

## Спецификации (ссылаться из задач)

### Модель данных

**accounts.User** (кастомный, от `AbstractUser`, логин по email)
- `email` (unique), `password`, `preferred_language` (`ru|uz|en`, default `ru`), `created_at`

**themes.Theme**
- `key` (slug, unique) — например `classic-white`
- `name` (переводимое: ru/uz/en)
- `category` — enum: `neutral | islamic | christian | secular`
- `layout_key` — дублирует `tokens.layout` для фильтрации (заполняется автоматически из `tokens`)
- `tokens` — JSONField, валидируется схемой ниже
- `preview_image` — ImageField
- `is_active` (bool), `sort_order` (int), `version` (int, инкремент при изменении `tokens`)
- `created_at`, `updated_at`

**themes.ThemeAsset**
- `theme` (FK), `key` (slug, уникален в пределах темы), `file` (ImageField/FileField), `kind` — `background | ornament | frame | icon`

**memorials.Memorial**
- `owner` (FK User)
- `first_name`, `last_name`, `middle_name` (опционально)
- `birth_date` (DateField, null), `birth_date_precision` (`day|month|year`)
- `death_date` (DateField, null), `death_date_precision` (`day|month|year`)
- при точности `year` хранится `YYYY-01-01`, при `month` — `YYYY-MM-01`
- `description` (TextField, до 10 000 символов, plain text с переносами строк)
- `language` (`ru|uz|en`) — язык интерфейса публичной страницы
- `theme` (FK Theme, PROTECT), `theme_overrides` (JSONField, default `{}`, в MVP не используется в UI)
- `short_code` (CharField 8, unique, **immutable**)
- `status` (`draft|published`), `published_at`
- `created_at`, `updated_at`

**memorials.Photo**
- `memorial` (FK), `original` (ImageField), `variants` (JSONField: `{"thumb": key, "medium": key, "large": key}` — ключи файлов в хранилище, URL собираются при отдаче)
- `caption` (опционально), `order` (int), `is_cover` (bool, максимум одна на страницу)
- `width`, `height`, `processing_status` (`pending|ready|failed`)

### short_code

- 8 символов из алфавита без неоднозначных символов: `23456789abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ`
- генерация криптостойким `secrets`, повтор при коллизии
- после создания изменить нельзя: проверка в `save()` + read-only в сериализаторах + тест

### Формат темы (`Theme.tokens`, schemaVersion 1)

```json
{
  "schemaVersion": 1,
  "layout": "classic",
  "layoutOptions": {
    "photoShape": "oval",
    "gallery": "grid"
  },
  "colors": {
    "background": "#F7F5F0",
    "surface": "#FFFFFF",
    "text": "#2B2B2B",
    "muted": "#7A7468",
    "accent": "#8C6D3F",
    "border": "#E2DDD3"
  },
  "fonts": {
    "heading": "Playfair Display",
    "body": "Inter"
  },
  "background": {
    "type": "color | image | gradient",
    "asset": "bg-main",
    "value": null,
    "overlay": "rgba(255,255,255,0.6)"
  },
  "ornaments": {
    "top": "ornament-top",
    "divider": "divider-1",
    "photoFrame": null
  },
  "radius": "12px"
}
```

Правила:
- `colors.*` — hex (`#rgb`, `#rrggbb`, `#rrggbbaa`) или `rgb()`/`rgba()`; все 6 ключей обязательны.
- `fonts.*` — только из белого списка шрифтов (список хранится в коде фронта и бэка, загружаются через `next/font`). Белый список: Playfair Display, Cormorant Garamond, EB Garamond, Lora, Merriweather, Noto Serif, Spectral, Inter, Montserrat, Noto Sans — все проверены на кириллицу, узбекские `ʻ`/`ʼ` (U+02BB/U+02BC) и ў/қ. Не подходят (нет U+02BB): Roboto, Open Sans, PT Serif, PT Sans, Manrope, Prata.
- `background.asset`, `ornaments.*` — ключи `ThemeAsset` этой темы или `null`, причём нужного `kind`: `background.asset` → `background`, `ornaments.top`/`divider` → `ornament`, `ornaments.photoFrame` → `frame`. Ключи `ornaments` необязательны.
- `background`: `type: image` → обязателен `asset`; `type: gradient` → обязателен `value` вида `linear-gradient(...)`/`radial-gradient(...)` без `;`, `{`, `}`, кавычек и `:` (значение попадает в CSS-переменную); `type: color` → `value` — цвет или `null` (тогда берётся `colors.background`). `overlay` — цвет или `null`.
- `radius` — `0`, `Npx` (до 3 цифр) или `N[.NN]rem`.
- `layoutOptions` (необязателен) валидируется схемой конкретного layout'а:
  - `classic`: `photoShape`: `oval | circle | rounded | square`; `gallery`: `grid | masonry`;
  - `gallery`: `galleryStyle`: `slider | masonry`; `descriptionPosition`: `side | below`.
- Лишние ключи на любом уровне запрещены (`additionalProperties: false`).
- Схема живёт в двух местах: `backend/apps/themes/schema.py` (JSON Schema) и `frontend/src/themes/schema.ts` (zod). Должен быть тест, сверяющий, что фикстурные темы проходят обе схемы.

### Интерфейс layout-компонента (фронт)

```ts
type LayoutProps = {
  memorial: PublicMemorial;   // данные страницы
  theme: ResolvedTheme;       // tokens + абсолютные URL ассетов
  locale: 'ru' | 'uz' | 'en';
};

type LayoutDefinition = {
  key: string;                          // 'classic'
  component: React.ComponentType<LayoutProps>;
  optionsSchema: z.ZodType;             // схема layoutOptions
  defaultOptions: Record<string, unknown>;
};

// src/themes/registry.ts
export const layouts: Record<string, LayoutDefinition>;
export function resolveLayout(key: string): LayoutDefinition; // fallback 'classic'
```

`tokens` превращаются в CSS-переменные (`--color-background`, `--font-heading`, `--radius` и т. д.) на корневом элементе страницы. Layout'ы используют только эти переменные.

### API (префикс `/api/v1/`)

| Метод | Путь | Описание |
|---|---|---|
| GET | `/auth/csrf/` | выставляет cookie `csrftoken` (её значение — в заголовке `X-CSRFToken` всех изменяющих запросов) |
| POST | `/auth/register/` | регистрация |
| POST | `/auth/login/` | вход, ставит httpOnly cookies |
| POST | `/auth/refresh/` | обновление access |
| POST | `/auth/logout/` | выход |
| GET | `/auth/me/` | текущий пользователь |
| GET, POST | `/memorials/` | свои страницы / создать |
| GET, PATCH, DELETE | `/memorials/{id}/` | своя страница |
| POST | `/memorials/{id}/publish/` | опубликовать |
| POST | `/memorials/{id}/unpublish/` | снять с публикации |
| POST | `/memorials/{id}/photos/` | загрузка фото (multipart) |
| PATCH | `/memorials/{id}/photos/reorder/` | порядок `[id, id, ...]` |
| PATCH, DELETE | `/memorials/{id}/photos/{photo_id}/` | подпись, cover / удалить |
| GET | `/memorials/{id}/qr/?format=svg\|png` | QR-код |
| GET | `/themes/?category=` | каталог активных тем (публичный) |
| GET | `/themes/{key}/` | тема с ассетами (публичный); `name` — объект `{ru, uz, en}` |
| GET | `/public/m/{short_code}/` | опубликованная страница + resolved theme |

- Все «свои» эндпоинты проверяют владельца (чужая страница → 404).
- Документация API: `drf-spectacular`, Swagger на `/api/docs/`.
- Типы фронта генерируются из OpenAPI (`openapi-typescript`).

### Маршруты фронта

- `/[locale]/` — лендинг (минимальный)
- `/[locale]/login`, `/[locale]/register`
- `/[locale]/dashboard` — список своих страниц
- `/[locale]/dashboard/memorials/new`
- `/[locale]/dashboard/memorials/[id]` — редактор (вкладки: данные, фото, оформление, публикация и QR)
- `/m/[code]` — **публичная страница, без префикса языка** (короткий URL для QR); язык интерфейса берётся из `memorial.language`

---

## Этап 0. Подготовка

- [x] **0.1 Каркас репозитория.** Структура из `CLAUDE.md`, `.gitignore`, `.editorconfig`, `.env.example`, README с запуском.
  - Критерии: структура папок создана, README описывает запуск.
  - Сделано: git-репозиторий (`main`, remote на GitHub), папки backend/frontend/.github по структуре (с `.gitkeep`), `.gitignore` (Python, Node/Next, env, Playwright), `.editorconfig` (2 пробела, 4 для Python), `.env.example` со всеми переменными инфраструктуры, JWT, URL и секретом ревалидации, README с описанием стека и запуска через `docker compose`.
- [x] **0.2 Docker Compose.** Сервисы: `postgres`, `redis`, `s3` на SeaweedFS (+ автосоздание bucket, анонимное чтение), `backend`, `worker`, `frontend`. Healthchecks.
  - Критерии: `docker compose up` поднимает всё, backend и frontend открываются в браузере.
  - Сделано: `docker-compose.yml` + dev-Dockerfile'ы backend/frontend. postgres, redis, s3 (+ `s3-init`: бакет создаётся идемпотентно; приложение пишет по ключу, аноним только читает — запись и листинг → 403), backend (миграции при старте, healthcheck `/api/health/`), worker (healthcheck `celery inspect ping`), frontend. Все сервисы healthy, backend и frontend открываются в браузере.
- [x] **0.3 Каркас Django.** Проект `config`, настройки base/dev/prod через `django-environ`, DRF, `drf-spectacular`, `django-storages` → S3 (SeaweedFS), CORS, Celery, `ruff`, `pytest`.
  - Критерии: `/api/docs/` открывается, тестовая Celery-задача выполняется, `pytest` и `ruff check` зелёные.
  - Сделано: Django 5.2 LTS (6.x пока не поддерживают simplejwt/django-storages/drf-spectacular), settings base/dev/prod на `django-environ`, DRF + `drf-spectacular` (`/api/schema/`, `/api/docs/`), `/api/health/` для healthcheck, S3-хранилище через `django-storages` с публичными URL из `MEDIA_PUBLIC_BASE_URL` (без подписей), CORS по умолчанию закрыт (прокси), Celery (`config.celery`, задача `ping` выполнена реальным worker'ом), минимальная кастомная `accounts.User` (до первой миграции; email-логин — в 1.1). Тесты: health, schema, swagger, ping, URL медиа. `ruff` (RUF001–003 отключены из-за кириллицы). Тесты и линт запускаются в контейнере: `docker compose exec backend pytest`.
- [x] **0.4 Каркас Next.js.** App Router, TS strict, ESLint, Prettier, Vitest, `next-intl` с ru/uz/en и роутингом `[locale]`, базовый layout кабинета.
  - Критерии: `/ru`, `/uz`, `/en` открываются с переведённой строкой, линт и тесты зелёные.
  - Сделано: Next.js 16.4 (`create-next-app`, `cacheComponents` включён по умолчанию шаблона), TS strict, ESLint + `eslint-config-prettier`, Prettier, Vitest. `next-intl` 4: `src/i18n/{routing,request,navigation}.ts`, локаль читается через `next/root-params`, а маршрутам вне `[locale]` (будущая `/m/[code]`) её можно передать явно. `src/proxy.ts` не трогает `/api` и `/m/...`. `next.config.ts` проксирует `/api/v1/*`, `/api/schema/`, `/api/docs/` на Django с сохранением завершающего «/». Лендинг и базовый layout кабинета (`/[locale]/dashboard`), переводы ru/uz/en, тест на совпадение ключей переводов. Скрипты: `lint`, `typecheck` (с `next typegen`), `test`, `format:check`.
- [x] **0.5 CI.** Пайплайн GitHub Actions: lint + tests для backend и frontend.
  - Критерии: пайплайн проходит на чистом репозитории.
  - Сделано: `.github/workflows/ci.yml` на push в `main` и PR. Job `backend`: Python 3.12 + uv, сервис Postgres, `ruff check`, `ruff format --check`, `makemigrations --check`, `pytest`. Job `frontend`: Node 22, `npm ci`, ESLint, Prettier, typecheck, Vitest, `next build`. Прогон на `e597bc4` зелёный. `setup-uv` закреплён точной версией: мажорных тегов у него нет.
- [x] **0.6** Заполнить раздел «Команды» в `CLAUDE.md`.

## Этап 1. Ядро бэкенда

- [x] **1.1 Пользователи и авторизация.** Кастомный User, эндпоинты `/auth/*`, JWT в httpOnly cookies, CSRF-защита для cookie-аутентификации.
  - Критерии: тесты на регистрацию, вход, refresh, logout, `me`; неавторизованный доступ к `/memorials/` → 401.
  - Сделано: `User` без `username`, логин по email (хранится и ищется в нижнем регистре), `preferred_language`, `created_at`; начальная миграция пересоздана (данных не было). Эндпоинты `/auth/register|login|refresh|logout|me/` + служебный `GET /auth/csrf/` (выставляет cookie `csrftoken`). Access — httpOnly cookie на `/`, refresh — httpOnly cookie только на `/api/v1/auth/`; `SameSite=Lax`, `Secure` в prod. Refresh ротируется, старый уходит в blacklist (`token_blacklist`), logout тоже его блеклистит. CSRF (double submit: cookie + `X-CSRFToken`) обязателен для всех изменяющих запросов, включая login/register. По умолчанию `IsAuthenticated` → аноним получает 401. 30 тестов (вкл. CSRF и атрибуты cookie), сценарий проверен вживую через прокси Next. **Тест «`/memorials/` → 401» добавить в 1.6**, когда появится эндпоинт.
- [x] **1.2 Модель тем.** `Theme`, `ThemeAsset`, JSON Schema токенов, валидация в `clean()` и сериализаторе, авто-заполнение `layout_key`, инкремент `version`.
  - Критерии: невалидные `tokens` не сохраняются (тесты на несколько видов ошибок), ссылка на несуществующий ассет — ошибка.
  - Сделано: `apps/themes` — `Theme` (переводимое `name` через modeltranslation: `name_ru` обязателен, fallback на ru), `ThemeAsset` (уникальный `key` в теме, файлы svg/png/jpg/webp). `schema.py`: JSON Schema + схемы `layoutOptions` по layout'ам + проверка ссылок на ассеты (существование и `kind`); ошибки в виде `tokens.colors.text: …`. `save()` всегда отклоняет невалидную структуру, заполняет `layout_key`, увеличивает `version` только при изменении `tokens`. Ссылки на ассеты проверяются в `clean()` и `ThemeSerializer` (не в `save()`: в админке тема сохраняется раньше inline-ассетов — учесть в 1.3). В тестах файлы хранятся в памяти (`conftest.py`), S3 не нужен. 53 теста тем, в т. ч. на CSS-инъекцию через градиент.
  - Решено: API каталога `/themes/` и `/themes/{key}/` делается вместе с 1.6 (нужен редактору в 3.5). Удаление используемого ассета запрещено в 1.3.
- [x] **1.3 Админка тем.** Django Admin: inline-ассеты, превью, фильтр по категории и активности, JSON-редактор для `tokens` с понятными ошибками валидации, переводимое `name`.
  - Критерии: тему можно создать полностью через админку.
  - Сделано: `ThemeAdmin` на `TranslationAdmin` (поля `name_ru/uz/en`), фильтры по категории, активности и layout, `is_active`/`sort_order` редактируются в списке, миниатюры превью в списке и в форме. `tokens` — textarea с отформатированным JSON, новая тема предзаполнена шаблоном, в подсказке перечислены layout'ы, шрифты и правила ссылок на ассеты; ошибки JSON и схемы показываются у поля с путём (`tokens.colors.text: …`). Inline-ассеты с превью; ссылки из `tokens` проверяются по данным формсета (`ThemeAssetInlineFormSet`), поэтому можно в одной отправке добавить ассет и сослаться на него, а удалить или переименовать используемый ассет нельзя. 11 тестов админки (создание темы целиком с переводами, превью и ассетами; ошибки; защита ассетов) + проверено вживую с загрузкой в S3.
- [x] **1.4 Фикстуры тем.** Management command `seed_themes`: 2 layout'а × 3–4 оформления (минимум 6 тем, разные категории) с ассетами-заглушками.
  - Критерии: команда идемпотентна, все темы проходят валидацию.
  - Сделано: 6 тем (classic: `classic-ivory`, `classic-emerald`, `classic-parchment`; gallery: `gallery-graphite`, `gallery-mist`, `gallery-night-sky`), все 4 категории, названия ru/uz/en. Данные — `backend/apps/themes/fixtures/themes.json` (его же будет читать тест фронта в 2.2), SVG-заглушки — `fixtures/assets/`, превью — PNG, рисуется из цветов темы. Логика в `apps/themes/seed.py`. По умолчанию создаются только отсутствующие темы (правки из админки не затираются); `--update` приводит существующие к фикстурам. Файлы перезаливаются только при изменении содержимого, `version` растёт только при изменении tokens, после сидинга `full_clean()` проверяет ссылки на ассеты. 13 тестов + проверено вживую: три запуска подряд, в S3 ровно 16 файлов, всё в версии 1.
- [ ] **1.5 Модель Memorial.** Поля, `short_code` (генерация + неизменяемость), даты с точностью, статусы.
  - Критерии: тест — `short_code` уникален и не меняется ни через модель, ни через API; тесты на валидацию дат (смерть не раньше рождения, нормализация при неполной точности).
  - Сделано: `apps/memorials` — `Memorial` по спецификации; `Language` вынесен в `apps/core/choices.py` (общий для User и Memorial). `short_code`: `secrets`, алфавит из 55 символов, повтор при коллизии (и при гонке на INSERT); задать вручную нельзя; изменение запрещено в `save()` **и триггером PostgreSQL** (миграция 0002 — ловит `QuerySet.update` и raw SQL; проверено мутацией). Даты: нормализация по точности в `save()`/`clean()`; смерть не раньше рождения — сравнение по более грубой точности («май 1950» и «1950 год» совместимы); даты не в будущем. `publish()`/`unpublish()`. 38 тестов. **Тест «`short_code` не меняется через API» — в 1.6** (сериализатора ещё нет).
- [x] **1.6 CRUD страниц.** ViewSet с проверкой владельца, publish/unpublish, тема по умолчанию при создании.
  - Критерии: тесты на доступ к чужой странице (404), на переключение темы, на публикацию.
  - Сделано: `MemorialViewSet` — queryset только своих страниц (чужая → 404 на всех методах, включая publish/unpublish), аноним → 401 (закрыт хвост из 1.1). Тема — по ключу, только активная; по умолчанию — первая активная по `sort_order`; текущая неактивная тема у страницы сохраняется. Язык по умолчанию — `preferred_language` владельца. Только для чтения: `short_code` (закрыт хвост из 1.5: PATCH/PUT его не меняют), `status`, `published_at`, `theme_overrides`. Даты проверяются моделью на итоговом состоянии (в т. ч. при частичном PATCH), модель принимает даты строкой. Плюс каталог тем `/themes/` (`?category=`), `/themes/{key}/` — публичные, только активные, `name` со всеми переводами. OpenAPI без предупреждений, общие enum `LanguageEnum`/`DatePrecisionEnum`. 32 теста API + проверено вживую через прокси Next.
- [x] **1.7 Фото.** Загрузка (jpeg/png/webp/heic, лимит размера), сохранение оригинала, Celery-задача: исправление EXIF-ориентации, удаление EXIF-геоданных, варианты `thumb/medium/large` в WebP. Сортировка, cover, удаление вместе с файлами.
  - Критерии: тесты задачи обработки, на единственный cover, на reorder; лимит 50 фото на страницу (51-я загрузка → 400).
  - Параметры (согласовано): до 20 МБ на файл; варианты WebP по длинной стороне thumb 320 / medium 1024 / large 2048 px, качество 82, без увеличения; HEIC через `pillow-heif` (настройки `PHOTO_*` в `base.py`).
  - Сделано: `Photo`; формат проверяется по содержимому, не по расширению. Оригинал хранится байт в байт (с EXIF) по случайному пути `photos/<uuid>/original.<ext>`, наружу (1.8) отдаются только варианты; варианты перекодированы без EXIF/XMP (GPS не утекает). Задача `process_photo` ставится после коммита; при ошибке — `failed`; пишет результат через `update()`, не затирая подпись. Лимит и порядок — под `select_for_update` страницы. Первое фото — обложка; удалили обложку — обложкой становится следующее; «не больше одной обложки» — ограничение в БД. `PATCH reorder/` принимает список id ровно всех фото страницы. Файлы удаляются после коммита (сигнал `post_delete`), в т. ч. каскадом при удалении страницы. `photos` добавлены в ответ страницы. 50 тестов.
  - Найдено при проверке вживую: (1) Next молча обрезал тело запроса до 10 МБ даже для `/api` — выставлен `experimental.proxyClientMaxBodySize: "25mb"`; (2) backend и worker собирались в два разных образа, worker оставался со старыми зависимостями — теперь общий образ `memorial-backend:dev`. Проверено: файл 11 МБ с поворотом и GPS через прокси → 201, обработан worker'ом, варианты без EXIF, удаление каскадом очищает S3.
- [x] **1.8 Публичный API.** `/public/m/{short_code}/`: только `published`, отдаёт данные страницы и resolved theme (tokens + абсолютные URL ассетов).
  - Критерии: черновик и несуществующий код → одинаковый 404, ответ содержит всё, что нужно для рендера, без лишних полей (email владельца и т. п. не утекают).
  - Формат ответа: `short_code`, ФИО, даты с точностью, `description`, `language`, `published_at`; `theme`: `{key, version, tokens, assets: {ключ ассета → абсолютный URL}}` — tokens без изменений (фронт резолвит ссылки по `assets` и валидирует той же zod-схемой); `photos`: только обработанные (`ready`), в порядке страницы, `{caption, is_cover, width, height, variants}`. Нет: владельца, email, внутренних id, оригиналов фото, `theme_overrides`, статусов.
  - Сделано: `PublicMemorialView` без аутентификации (протухшая cookie не даёт 401), только `published`; черновик и неизвестный код — побайтно одинаковый 404 без имени модели. Неактивная тема у опубликованной страницы продолжает отдаваться. Число SQL-запросов не растёт с числом фото и ассетов. 11 тестов (в т. ч. точный набор ключей и поиск email/оригиналов в теле ответа) + проверено вживую через прокси Next.
- [x] **1.9 QR.** Генерация `segno`: SVG и PNG (печатное качество), коррекция ошибок H, URL вида `{PUBLIC_BASE_URL}/m/{code}`.
  - Критерии: тест декодирует сгенерированный QR и сверяет URL.
  - Сделано: `apps/memorials/qr.py` + `GET /memorials/{id}/qr/?format=svg|png` (по умолчанию svg; только владелец, доступен и для черновика — QR нужен до гравировки). Уровень H строго (`boost_error=False`), поле 4 модуля. SVG — вектор с `viewBox` без фиксированного размера; PNG — 20 px/модуль (~820 px) с 300 dpi. `Content-Disposition` с именем файла, `Cache-Control: private` (код неизменяем). `?format=` в DRF зарезервирован под выбор рендерера — отключено (`URL_FORMAT_OVERRIDE: None`). Тесты декодируют и PNG, и SVG (`zxing-cpp` — только в dev, без системных библиотек; SVG растеризуется в тесте мини-растеризатором путей segno) и сверяют URL и уровень H. 12 тестов + проверено вживую через прокси.
- [x] **1.10 Ревалидация.** Сигналы: при изменении `Memorial`, `Photo` или `Theme` — Celery-задача вызывает `POST {FRONTEND_URL}/api/revalidate` с секретом и тегами `memorial:{code}` / `theme:{key}`.
  - Критерии: тест, что задача ставится в очередь с правильными тегами.
  - Сделано: `apps/core` (теперь Django-приложение): `revalidation.py` + задача `revalidate_tags`. Сигналы `post_save`/`post_delete` на `Memorial`, `Photo`, `Theme`, `ThemeAsset` копят теги, после коммита ставится одна задача на все теги транзакции (откат — ничего не уходит). Явные вызовы там, где сигналов нет: окончание обработки фото (`update()`), сортировка (`bulk_update()`). Смена `key` темы ревалидирует старый и новый тег. Повторы с нарастающей паузой при недоступности фронта и 5xx (до 8 раз); 4xx — в лог без повторов. 18 тестов (в т. ч. мутацией проверен вызов после обработки фото) + проверено вживую: worker отправляет запрос во frontend-контейнер.

## Этап 2. Движок тем на фронте

- [ ] **2.1 API-клиент.** Прокси `/api/v1/*` → Django через `rewrites` в `next.config`, генерация типов из OpenAPI, тонкий типизированный клиент (server и client side), обработка 401 с refresh.
- [ ] **2.2 Схема и токены.** zod-схема `tokens`, функция `tokensToCssVars()`, белый список шрифтов через `next/font`.
  - Критерии: unit-тесты на преобразование токенов и на отклонение невалидных тем.
  - Фикстурные темы для теста обеих схем: `backend/apps/themes/fixtures/themes.json` (бэкенд их уже проверяет в `test_seed.py`).
- [ ] **2.3 Реестр layout'ов.** `registry.ts`, `resolveLayout()` с fallback, валидация `layoutOptions`.
  - Критерии: unit-тест на fallback при неизвестном ключе.
- [ ] **2.4 Общие блоки.** Компоненты, из которых собираются layout'ы: `PersonHeader` (фото, ФИО), `LifeDates` (форматирование по точности и языку), `Description`, `Gallery` (с лайтбоксом), `Ornament`. Используют только CSS-переменные.
  - Предложение из 1.4: ассеты-орнаменты (`kind: ornament`) — одноцветные SVG, `Ornament` выводит их через CSS `mask-image` с цветом `var(--color-accent)` (форма — из ассета, цвет — из tokens). Фоны (`background`) и рамки (`frame`) — обычные изображения со своими цветами.
  - Критерии: unit-тесты `LifeDates` для всех комбинаций точности и трёх языков.
- [ ] **2.5 Layout `classic`.** Центрированная композиция: главное фото, ФИО, даты, орнамент-разделитель, описание, сетка галереи.
- [ ] **2.6 Layout `gallery`.** Акцент на фото: большое главное фото, слайдер или masonry, описание сбоку или ниже.
- [ ] **2.7 Публичная страница `/m/[code]`.** Серверный рендер, `fetch` с тегами для on-demand revalidate, `robots: noindex, nofollow`, OG-теги (имя, даты, главное фото); для черновиков и несуществующих кодов — дружелюбная страница «Страница недоступна» с HTTP 404. Route handler `/api/revalidate` с проверкой секрета.
  - Критерии: страница отдаёт полностью готовый HTML, превью ссылки в Telegram корректное, изменение страницы видно сразу после ревалидации.
  - Контракт с бэком (1.10): `POST /api/revalidate`, заголовок `X-Revalidate-Secret: {REVALIDATE_SECRET}`, тело `{"tags": ["memorial:<code>", "theme:<key>", ...]}`. Неверный секрет → 401 (бэк не повторяет 4xx), ошибка → 5xx (бэк повторит). Данные страницы кешировать с тегами `memorial:<code>` **и** `theme:<key>` её темы — правка темы в админке должна обновлять все страницы с ней.
- [ ] **2.8 Песочница тем (dev-only).** Страница `/dev/themes`, где все темы рендерятся на фиктивных данных — для быстрой проверки новых тем.

## Этап 3. Личный кабинет

- [ ] **3.1 Авторизация в UI.** Формы регистрации и входа (валидация, ошибки с бэка, переводы), защита `/dashboard` в middleware.
- [ ] **3.2 Список страниц.** Карточки: фото, имя, статус, быстрые действия.
- [ ] **3.3 Редактор: данные.** Форма ФИО, даты с выбором точности, описание, язык страницы. Автосохранение с задержкой (debounce), индикатор «Сохранение… / Сохранено / Ошибка».
- [ ] **3.4 Редактор: фото.** Мультизагрузка с прогрессом, drag & drop сортировка, выбор главного фото, подписи, удаление, статус обработки.
- [ ] **3.5 Редактор: оформление.** Каталог тем с фильтром по категории, живой предпросмотр выбранной темы на данных пользователя (тот же layout-компонент, что и на публичной странице), применение в один клик.
- [ ] **3.6 Публикация и QR.** Публикация и снятие, ссылка с копированием, предпросмотр QR, скачивание SVG и PNG, кнопка «поделиться».

## Этап 4. Полировка и запуск

- [ ] **4.1 Переводы.** Полное покрытие ru/uz/en, проверка отсутствующих ключей в CI.
- [ ] **4.2 Мобильная адаптация.** Публичная страница и редактор на ширине 360px; Lighthouse публичной страницы ≥ 90 по Performance на мобильном.
- [ ] **4.3 Безопасность.** Rate limit на auth и загрузку, проверка MIME фото, заголовки безопасности, удаление аккаунта со всеми данными.
- [ ] **4.4 Прод-окружение.** Production Dockerfile'ы, reverse proxy с HTTPS, переменные окружения, CDN для медиа — хостинг пока не определён, не начинать без согласования.
  - ⚠️ `PUBLIC_BASE_URL` зашивается в QR, а QR гравируется на камне: окончательный домен (со схемой `https://`) должен быть выставлен **до** первой реальной гравировки и после этого не меняться никогда. Продлевать домен бессрочно.
- [ ] **4.5 Бэкапы.** Ежедневный бэкап Postgres и бакета с фото в отдельное хранилище, проверенная процедура восстановления (описать в README).
- [ ] **4.6 Мониторинг.** Sentry на бэке и фронте, логи Celery.
- [ ] **4.7 Юридическое.** Страницы политики конфиденциальности и условий использования (тексты предоставит владелец, сделать каркас).
- [ ] **4.8 E2E smoke-тест.** Playwright: регистрация → создание страницы → загрузка фото → смена темы → публикация → открытие `/m/[code]`.

---

## После MVP (не делать без отдельной задачи)

- Больше layout'ов и тем, поиск по каталогу
- Монетизация: премиум-темы, заказ таблички с QR, Payme / Click
- Свечи, книга памяти
- Несколько редакторов одной страницы
- Видео, аудио, таймлайн жизни
- Вход по телефону через SMS
