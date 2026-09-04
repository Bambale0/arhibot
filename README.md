# Arhibot MVP

AI architecture MVP for web and Telegram Mini App.

## Repository layout

- `backend/` — FastAPI API, auth, projects, local media storage, PostgreSQL/Redis, Alembic.
- `frontend/` — React/Vite client for auth, projects, upload and generation workspace UX.
- `backend/app/telegram_bot/` — thin Telegram bot that opens the frontend as a Mini App.
- `.github/workflows/ci.yml` — CI for backend contracts/integration and frontend production build.

## Current MVP scope

Implemented now:

- email + Telegram authentication foundation;
- Telegram `/start` and `/app` commands with **Open application** WebApp button;
- persistent Telegram menu button that opens the Mini App;
- projects CRUD with ownership;
- local image uploads served through the product's public static domain;
- JPEG/PNG/WebP validation;
- responsive web / Telegram Mini App client;
- generation workspace UI with an explicit demo flag until generation endpoints are connected.

Not in MVP: S3/presigned uploads, Ideas, Favorites, Broadcasts, billing, advanced admin/RBAC.

## Telegram bot / Mini App

The same deployed frontend is used for both browser and Telegram. When Telegram opens it through a `web_app` button, Telegram injects `initData`, and the frontend authenticates through `/api/v1/auth/telegram`.

Production `.env` must contain:

```env
TELEGRAM_BOT_TOKEN=<token from BotFather>
TELEGRAM_WEBAPP_URL=https://<public-frontend-domain>
```

`TELEGRAM_WEBAPP_URL` must be HTTPS.

The `bot` Docker service runs:

```bash
python -m app.telegram_bot.main
```

On startup it configures:

- `/start` — welcome message + **Open application** Mini App button;
- `/app` — same Mini App launcher;
- Telegram chat menu button — **Open application**.

For a server already running the repository, deploy the new `main` and restart the bot service:

```bash
git pull origin main
cd backend
docker compose up -d --build bot api nginx
```

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
