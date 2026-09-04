# Arhibot MVP

AI architecture MVP for web and Telegram Mini App.

## Repository layout

- `backend/` — FastAPI API, auth, projects, local media storage, PostgreSQL/Redis, Alembic.
- `frontend/` — React/Vite client for auth, projects, upload and generation workspace UX.
- `.github/workflows/ci.yml` — CI for backend contracts/integration and frontend production build.

## Current MVP scope

Implemented now:

- email + Telegram authentication foundation;
- projects CRUD with ownership;
- local image uploads served through the product's public static domain;
- JPEG/PNG/WebP validation;
- responsive web / Telegram Mini App client;
- generation workspace UI with an explicit demo flag until generation endpoints are connected.

Not in MVP: S3/presigned uploads, Ideas, Favorites, Broadcasts, billing, advanced admin/RBAC.

## Backend

```bash
cd backend
cp .env.example .env
docker compose up --build
```

API: `http://localhost:8000/api/v1`

Swagger: `http://localhost:8000/docs`

## Frontend

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

By default Vite proxies `/api` to `http://localhost:8000`.

## CI

GitHub Actions runs on every push and pull request to `main`:

1. backend compile + unit/contract tests;
2. OpenAPI contract export succeeds;
3. PostgreSQL + Redis integration job with Alembic migrations;
4. frontend TypeScript check + production Vite build.

No production secrets are stored in the workflow; CI uses disposable test credentials only.
