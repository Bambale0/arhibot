# AI Architecture Backend — MVP core

Рабочий backend-каркас для клиентского MVP. Он сохраняет правильную границу продукта (`FastAPI API -> services -> repositories/providers`), но без S3, Ideas/Admin, сложного provider router и другой инфраструктуры, которая сейчас не нужна заказчику.

## Что уже есть

### Foundation + auth

- Python 3.12+
- FastAPI `/api/v1`
- OpenAPI `/openapi.json`, Swagger `/docs`, ReDoc `/redoc`
- PostgreSQL + SQLAlchemy 2 async + Alembic
- Redis dependency для следующего шага с worker/queue
- `X-Request-ID`
- единый `application/problem+json`
- email register/login
- Telegram Mini App auth
- JWT access + rotating refresh token
- `/api/v1/me`

### Projects

```text
POST   /api/v1/projects
GET    /api/v1/projects
GET    /api/v1/projects/{project_id}
PATCH  /api/v1/projects/{project_id}
DELETE /api/v1/projects/{project_id}
```

- UUID
- ownership по `current_user.id`
- soft delete
- cursor pagination
- typed project context: площадь дома/участка, этажи, спальни, санузлы, стиль

### Assets — локальный сервер, без S3

```text
POST   /api/v1/assets
GET    /api/v1/assets/{asset_id}
DELETE /api/v1/assets/{asset_id}
```

`POST /assets` принимает `multipart/form-data`:

- `file` — JPEG / PNG / WebP
- `purpose` — `generation_input` или `project_reference`
- `project_id` — optional UUID

Backend:

1. проверяет ownership проекта;
2. ограничивает размер файла;
3. проверяет реальные байты изображения через Pillow, а не доверяет расширению;
4. получает width/height;
5. создаёт UUID имени файла;
6. пишет файл в persistent Docker volume;
7. сохраняет metadata в PostgreSQL;
8. возвращает публичный URL вида `https://media.example.com/uploads/users/...`.

В production Nginx читает volume в read-only режиме. Запись файлов по HTTP запрещена: только API-процесс может писать в media volume.

## Local media deployment

Основные настройки:

```text
MEDIA_ROOT=/data/media
MEDIA_PUBLIC_BASE_URL=http://localhost:8000
MAX_IMAGE_SIZE_BYTES=20971520
MAX_IMAGE_PIXELS=80000000
```

Локальный `docker-compose.yml` монтирует один named volume:

```text
api   -> /data/media      read/write
nginx -> /srv/media       read-only
```

Nginx отдаёт его по `/uploads/`.

Для отдельного публичного media-домена есть пример:

```text
deploy/nginx-media-domain.conf.example
```

В production достаточно выставить, например:

```text
MEDIA_PUBLIC_BASE_URL=https://media.example.com
```

и примонтировать тот же media-каталог к Nginx.

## Пример flow для frontend

Создать проект:

```bash
curl -X POST http://localhost:8000/api/v1/projects \
  -H 'Authorization: Bearer ACCESS_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "name":"Дом у озера",
    "context":{"house_area_m2":160,"floors":2,"plot_area_m2":1000}
  }'
```

Загрузить фотографию:

```bash
curl -X POST http://localhost:8000/api/v1/assets \
  -H 'Authorization: Bearer ACCESS_TOKEN' \
  -F 'purpose=generation_input' \
  -F 'project_id=PROJECT_UUID' \
  -F 'file=@room.jpg'
```

Ответ:

```json
{
  "id": "uuid",
  "project_id": "uuid",
  "type": "image",
  "purpose": "generation_input",
  "original_filename": "room.jpg",
  "mime_type": "image/jpeg",
  "size_bytes": 4198234,
  "width": 1920,
  "height": 1080,
  "url": "https://media.example.com/uploads/users/.../asset.jpg",
  "created_at": "2026-09-03T13:00:00Z"
}
```

## Запуск

```bash
cp .env.example .env
docker compose up -d postgres redis
docker compose run --rm api alembic upgrade head
docker compose up --build
```

После запуска:

```text
http://localhost:8000/docs
http://localhost:8000/openapi.json
http://localhost:8000/health/live
http://localhost:8000/health/ready
```

## Миграции

```text
20260903_0001_users_auth.py
20260903_0002_projects_assets.py
```

Проверить цепочку:

```bash
alembic history
```

Применить:

```bash
alembic upgrade head
```

## Тесты

```bash
pip install -e '.[dev]'
pytest -q
```

Текущий unit/contract набор проверяет auth, OpenAPI, модели, cursor pagination, image validation и безопасный local storage path.

PostgreSQL integration test opt-in:

```bash
RUN_INTEGRATION_TESTS=1 pytest -q -m integration
```

## OpenAPI

Экспорт контракта:

```bash
python scripts/export_openapi.py
```

Текущие operation IDs для нового MVP-среза:

```text
createProject
listProjects
getProject
updateProject
deleteProject
uploadAsset
getAsset
deleteAsset
```

## Что специально НЕ делаем сейчас

- S3 / presigned uploads
- Ideas / Favorites / Admin Ideas
- Broadcasts
- Google / Apple auth implementation
- billing / credit ledger
- сложный ProviderRouter
- SSE
- отдельную микросервисную архитектуру

## Следующий шаг MVP

Следующий слой — `Generation`:

```text
POST /api/v1/generations/facades
POST /api/v1/generations/interiors
POST /api/v1/generations/interior-redesigns
GET  /api/v1/generations/{generation_id}
GET  /api/v1/generations
```

Для первой версии нужен один реальный image provider, worker и четыре публичных статуса:

```text
queued -> processing -> completed | failed
```

Provider получает публичные asset URLs, а готовые изображения backend скачивает в тот же локальный media storage и регистрирует как `generation_output` assets.
