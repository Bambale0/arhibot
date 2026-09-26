# AuRoom — AI Architecture Platform

> ✅ **Image-based MVP release candidate**
>
> FastAPI · PostgreSQL · Redis · React/Vite · Telegram Mini App · billing · admin control plane
>
> Repository codename: `arhibot`.

AuRoom is an architecture-focused AI product for planning houses, facades, master plans and interior spaces. The approved MVP is centered on image generation and Telegram Mini App workflows; public 3D is intentionally outside the current release scope.

The current integration line is `dev`. Production promotion is performed only through an explicit `dev -> main` release after acceptance checks.

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
          +--> projects / questionnaires
          +--> generation orchestration
          +--> billing
          +--> Ideas / History
          +--> admin control plane
          |
          +--> PostgreSQL
          +--> Redis
          +--> media storage
          +--> AI provider adapters
```

## MVP scope

The current image-based MVP includes:

- email and Telegram authentication;
- Telegram Mini App launch, safe-area and fullscreen flows;
- project ownership, dashboard and project lifecycle;
- questionnaire-driven architecture briefs;
- initial image generation and refinement flows;
- personal History and public Ideas feed;
- signed/private media delivery and optimized feed previews;
- credit balance and YooKassa billing flows;
- authenticated web admin control plane;
- admin AI Sandbox and low-cost Bird flyover GIF experiment;
- PostgreSQL/Redis migrations, queues, worker recovery and runtime health checks;
- encrypted off-site backup/recovery tooling;
- CI covering backend, integration and browser/frontend verification.

Public 3D/GLB rendering is not part of the approved MVP and remains disabled in normal runtime.

## Release status

As of **2026-09-24**, the verified `dev` baseline is:

- commit `b55fff1cbd7e66945df28032f5289f3c7ec38be2`;
- CI run `35842676884`: backend tests, backend integration and frontend build — success;
- development deploy run `35843724041` — success;
- deployed-server smoke run `35844018736` — success.

The repository is ready for final product acceptance of the approved MVP scope. Before production promotion, run the environment-specific acceptance path that exercises any real paid provider/billing behavior required for launch, then promote `dev` to `main` only with explicit operator approval.

Operational features such as distributed tracing, long-duration provider soak testing and blue-green/canary deployment remain later-stage infrastructure improvements rather than blockers for the current MVP handoff.

## Repository layout

```text
backend/                    # FastAPI backend and infrastructure
frontend/                   # React/Vite product UI
backend/app/telegram_bot/   # Telegram launcher/channel adapter
.github/workflows/          # CI, dev deployment and smoke verification
ops/                        # deploy, backup, restore and runtime operations
docs/                       # product, release and operations documentation
AGENTS.md                    # repository engineering rules
CONTEXT.md                   # domain terminology
```

## Release and operations documentation

- `docs/production-readiness-2026-09-22.md` — production-readiness evidence and remaining release boundaries.
- `docs/operations-hardening.md` — runtime preflight, backup/recovery, monitoring and deployment constraints.
- `docs/agents/EXECUTION.md` — current release status plus historical engineering execution ledger.
- `docs/frontend-layout-audit-2026-09-22.md` — responsive/browser verification evidence.
