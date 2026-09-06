# AuRoom — AI Architecture Platform

> 🚧 **Work in progress / active development**
>
> FastAPI · PostgreSQL · Redis · React/Vite · Telegram Mini App · billing · admin control plane
>
> Repository codename: `arhibot`.

AuRoom is an architecture-focused AI product for planning houses, facades, master plans and interior spaces. The project is being built backend-first so the same API can serve Telegram today and an independent web product later.

This repository is intentionally **not presented as a finished portfolio flagship yet**. It is public to show active product development and architecture decisions while the main user flows are still being completed.

## Current architecture

```text
Web / Telegram Mini App
          |
          v
      React/Vite
          |
          v
       FastAPI
          |
          +--> auth / users
          +--> projects
          +--> generation orchestration
          +--> billing
          +--> admin control plane
          |
          +--> PostgreSQL
          +--> Redis
          +--> media storage
          +--> AI provider adapters
```

## Current scope

The codebase includes foundations for:

- email and Telegram authentication;
- Telegram Mini App launch flows;
- project ownership and CRUD;
- generation-oriented product flows;
- billing and admin operations;
- PostgreSQL/Redis infrastructure;
- Alembic migrations;
- React/Vite customer UI;
- CI for backend and frontend verification.

## Repository layout

```text
backend/                    # FastAPI backend and infrastructure
frontend/                   # React/Vite product UI
backend/app/telegram_bot/   # thin Telegram launcher/channel adapter
.github/workflows/          # CI
AGENTS.md                    # repository engineering rules
CONTEXT.md                   # domain terminology
```

## Development status

The project is actively evolving. Public interfaces, generation contracts and UX may change before the first stable release.

For portfolio review, the completed production projects on this GitHub profile currently provide a better representation of production readiness; AuRoom is the example of an actively developed backend-first product.
