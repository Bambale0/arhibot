# AuRoom MVP

AI architecture MVP for web and Telegram Mini App.

## Repository layout

- `backend/` — FastAPI API, auth, projects, billing, admin control plane, local media storage, PostgreSQL/Redis, Alembic.
- `frontend/` — React/Vite client for projects, ideas, generation, history, profile, billing and web admin.
- `backend/app/telegram_bot/` — thin Telegram bot that opens AuRoom as a Mini App.
- `.github/workflows/ci.yml` — CI for backend contracts/integration and frontend production build.
- `AGENTS.md` — mandatory repository rules for agents, skills and business configuration.
- `CONTEXT.md` — AuRoom domain terminology.

## Current MVP scope

Implemented:

- email + Telegram authentication foundation;
- Telegram Mini App launcher and persistent menu button;
- projects CRUD with ownership;
- local image uploads served through the public domain;
- JPEG/PNG/WebP validation;
- responsive web / Telegram Mini App client;
- four generation scenarios: floor plan, facade, master plan and interior;
- Redis generation worker and server-side history;
- NexusAPI provider integration with DB-managed primary/fallback models, model parameters and prompts;
- DB-backed Ideas feed;
- YooKassa payment flow and user credit balance;
- authenticated web admin for tariffs, ideas, AI runtime/prompts, users/credits, payments, broadcasts and audit.

Not in this MVP: S3/presigned uploads, favorites, complex billing subscriptions or enterprise RBAC.

## Business configuration

Normal product/business configuration is stored in PostgreSQL and managed through the authenticated web admin. Do not put tariffs, prices, ideas, model selection, prompt content or broadcasts in code or environment variables.

Provider and cryptographic credentials remain server-side secrets. The web admin may show only safe configured/not-configured state; it never exposes secret values.

Current server-only credentials include:

```env
TELEGRAM_BOT_TOKEN=
NEXUS_API_KEY=
YOOKASSA_SHOP_ID=
YOOKASSA_SECRET_KEY=
JWT_SECRET=
REFRESH_TOKEN_SECRET=
```

See `.env.example` for infrastructure settings.

## Telegram bot / Mini App

The same deployed frontend is used for browser and Telegram. Telegram injects `initData`; the frontend authenticates through `/api/v1/auth/telegram` and does not require an email login inside the Mini App.

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

## Web admin

Backend authorization is authoritative. `/api/v1/admin/*` requires a user role of `admin` or `superadmin`; role-changing operations require `superadmin` where appropriate.

The control plane manages:

- tariffs and their active state/order;
- Ideas feed entries;
- generation primary/fallback models and provider parameters;
- per-scenario prompt templates;
- users, account state, roles and audited credit adjustments;
- YooKassa payment visibility/reconciliation;
- Telegram broadcast campaigns;
- Telegram bot public content/branding;
- audit log.

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
2. OpenAPI contract export;
3. PostgreSQL + Redis integration tests with Alembic migrations;
4. frontend TypeScript check + production Vite build.

No production secrets are stored in the workflow; CI uses disposable test credentials only.


## Runtime backup and recovery

Production deploys create a PostgreSQL + media backup before migrations. A root cron entry also runs `ops/backup_runtime.sh` on the cadence stored in **Operational Settings** in web admin.

Backups can be checked without changing runtime state:

```bash
./ops/restore_runtime.sh /root/arhibot /root/arhibot/backups/runtime/<timestamp> VERIFY
```

An actual restore is intentionally destructive and requires the explicit third argument `RESTORE`. Never use it as a health check; use `VERIFY` instead.
