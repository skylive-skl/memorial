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
- `colors.*` — hex или rgba; все 6 ключей обязательны.
- `fonts.*` — только из белого списка шрифтов (список хранится в коде фронта и бэка, загружаются через `next/font`).
- `background.asset`, `ornaments.*` — ключи `ThemeAsset` этой темы или `null`.
- `layoutOptions` валидируются схемой конкретного layout'а.
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
| GET | `/themes/?category=` | каталог активных тем |
| GET | `/themes/{key}/` | тема с ассетами |
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
- [ ] **0.5 CI.** Пайплайн GitHub Actions: lint + tests для backend и frontend.
  - Критерии: пайплайн проходит на чистом репозитории.
- [ ] **0.6** Заполнить раздел «Команды» в `CLAUDE.md`.

## Этап 1. Ядро бэкенда

- [ ] **1.1 Пользователи и авторизация.** Кастомный User, эндпоинты `/auth/*`, JWT в httpOnly cookies, CSRF-защита для cookie-аутентификации.
  - Критерии: тесты на регистрацию, вход, refresh, logout, `me`; неавторизованный доступ к `/memorials/` → 401.
- [ ] **1.2 Модель тем.** `Theme`, `ThemeAsset`, JSON Schema токенов, валидация в `clean()` и сериализаторе, авто-заполнение `layout_key`, инкремент `version`.
  - Критерии: невалидные `tokens` не сохраняются (тесты на несколько видов ошибок), ссылка на несуществующий ассет — ошибка.
- [ ] **1.3 Админка тем.** Django Admin: inline-ассеты, превью, фильтр по категории и активности, JSON-редактор для `tokens` с понятными ошибками валидации, переводимое `name`.
  - Критерии: тему можно создать полностью через админку.
- [ ] **1.4 Фикстуры тем.** Management command `seed_themes`: 2 layout'а × 3–4 оформления (минимум 6 тем, разные категории) с ассетами-заглушками.
  - Критерии: команда идемпотентна, все темы проходят валидацию.
- [ ] **1.5 Модель Memorial.** Поля, `short_code` (генерация + неизменяемость), даты с точностью, статусы.
  - Критерии: тест — `short_code` уникален и не меняется ни через модель, ни через API; тесты на валидацию дат (смерть не раньше рождения, нормализация при неполной точности).
- [ ] **1.6 CRUD страниц.** ViewSet с проверкой владельца, publish/unpublish, тема по умолчанию при создании.
  - Критерии: тесты на доступ к чужой странице (404), на переключение темы, на публикацию.
- [ ] **1.7 Фото.** Загрузка (jpeg/png/webp/heic, лимит размера), сохранение оригинала, Celery-задача: исправление EXIF-ориентации, удаление EXIF-геоданных, варианты `thumb/medium/large` в WebP. Сортировка, cover, удаление вместе с файлами.
  - Критерии: тесты задачи обработки, на единственный cover, на reorder; лимит 50 фото на страницу (51-я загрузка → 400).
- [ ] **1.8 Публичный API.** `/public/m/{short_code}/`: только `published`, отдаёт данные страницы и resolved theme (tokens + абсолютные URL ассетов).
  - Критерии: черновик и несуществующий код → одинаковый 404, ответ содержит всё, что нужно для рендера, без лишних полей (email владельца и т. п. не утекают).
- [ ] **1.9 QR.** Генерация `segno`: SVG и PNG (печатное качество), коррекция ошибок H, URL вида `{PUBLIC_BASE_URL}/m/{code}`.
  - Критерии: тест декодирует сгенерированный QR и сверяет URL.
- [ ] **1.10 Ревалидация.** Сигналы: при изменении `Memorial`, `Photo` или `Theme` — Celery-задача вызывает `POST {FRONTEND_URL}/api/revalidate` с секретом и тегами `memorial:{code}` / `theme:{key}`.
  - Критерии: тест, что задача ставится в очередь с правильными тегами.

## Этап 2. Движок тем на фронте

- [ ] **2.1 API-клиент.** Прокси `/api/v1/*` → Django через `rewrites` в `next.config`, генерация типов из OpenAPI, тонкий типизированный клиент (server и client side), обработка 401 с refresh.
- [ ] **2.2 Схема и токены.** zod-схема `tokens`, функция `tokensToCssVars()`, белый список шрифтов через `next/font`.
  - Критерии: unit-тесты на преобразование токенов и на отклонение невалидных тем.
- [ ] **2.3 Реестр layout'ов.** `registry.ts`, `resolveLayout()` с fallback, валидация `layoutOptions`.
  - Критерии: unit-тест на fallback при неизвестном ключе.
- [ ] **2.4 Общие блоки.** Компоненты, из которых собираются layout'ы: `PersonHeader` (фото, ФИО), `LifeDates` (форматирование по точности и языку), `Description`, `Gallery` (с лайтбоксом), `Ornament`. Используют только CSS-переменные.
  - Критерии: unit-тесты `LifeDates` для всех комбинаций точности и трёх языков.
- [ ] **2.5 Layout `classic`.** Центрированная композиция: главное фото, ФИО, даты, орнамент-разделитель, описание, сетка галереи.
- [ ] **2.6 Layout `gallery`.** Акцент на фото: большое главное фото, слайдер или masonry, описание сбоку или ниже.
- [ ] **2.7 Публичная страница `/m/[code]`.** Серверный рендер, `fetch` с тегами для on-demand revalidate, `robots: noindex, nofollow`, OG-теги (имя, даты, главное фото); для черновиков и несуществующих кодов — дружелюбная страница «Страница недоступна» с HTTP 404. Route handler `/api/revalidate` с проверкой секрета.
  - Критерии: страница отдаёт полностью готовый HTML, превью ссылки в Telegram корректное, изменение страницы видно сразу после ревалидации.
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
