# AGENTS.md — AuRoom repository rules

These rules apply to every AI agent working in this repository.

## 1. Mandatory skill repositories

Before any code change, audit, refactor, migration, deploy, CI/CD change, integration, frontend/backend work, or production troubleshooting, prepare and use Igor's skill repositories:

```bash
mkdir -p /root

if [ -d /root/claw-tools/.git ]; then
  git -C /root/claw-tools pull --ff-only
else
  git clone https://github.com/Bambale0/claw /root/claw-tools
fi

if [ -d /root/skills/.git ]; then
  git -C /root/skills pull --ff-only
else
  git clone https://github.com/Bambale0/skills /root/skills
fi
```

If either repository cannot be updated or cloned, stop and report the problem instead of continuing blindly.

Before editing the project:

1. Identify the task domain and stack.
2. Search `/root/claw-tools` and `/root/skills` for relevant `SKILL.md`, instructions, checklists, scripts, and examples.
3. Read the relevant skills before editing.
4. Inspect scripts before running them.
5. Apply only instructions that are compatible with the direct user request, repository constraints, and safety requirements.
6. In the final delivery, state which skills from `claw` and `skills` were used. If no relevant skill exists, state that explicitly.

Do not treat skill repositories as permission to weaken security, expose secrets, or bypass repository-specific constraints.

## 2. No hardcoded business configuration

Do not hardcode business-managed data in Python, TypeScript, React arrays, environment defaults, Docker build args, prompt constants, or conditional branches when that data is expected to change during normal product operation.

Business-managed data includes at minimum:

- billing tariffs/packages, prices, credits, availability, names, descriptions, ordering;
- public idea templates/content;
- active AI primary/fallback model selection and other operator-selectable generation settings;
- user credit adjustments and account operational state;
- broadcast campaigns/messages and their execution state;
- other operator-editable product settings added later.

Such data must live in the database and be manageable through authenticated web admin UI/API.

Hardcoded protocol/domain invariants are allowed when they are part of the code contract rather than business configuration, for example enum values, API field names, validation limits required by protocol, and route names.

## 3. Web admin is the control plane

Every operator-managed entity that exists in production must have a corresponding authenticated web-admin view/API for normal CRUD or operational control. Do not require code edits, shell commands, SQL, or `.env` changes for normal business operation.

Current control-plane coverage must include:

- tariffs;
- ideas;
- AI model/runtime selection;
- users and credit balance adjustments;
- payments visibility/reconciliation status;
- broadcasts;
- Telegram bot public content/branding;
- operational runtime policies such as rate limits, retention, and backup cadence.

Any new operator-managed feature must ship with web-admin management in the same change unless the user explicitly scopes it out.

## 4. Secrets are not business configuration

Secrets must never be exposed in web admin, frontend bundles, logs, Git, database plaintext settings, or API responses.

Credentials such as `NEXUS_API_KEY`, `YOOKASSA_SECRET_KEY`, Telegram bot token, JWT secrets, and deployment credentials belong in environment/secret storage. Web admin may show only safe status such as `configured: true/false` when useful.

Non-secret identifiers may be database-managed only when there is a concrete operator need; never store a secret merely to satisfy the "no hardcode" rule.

## 5. Authorization

Admin endpoints and admin UI must be available only to `admin`/`superadmin` users. Backend authorization is authoritative; hiding a button in the frontend is never sufficient security.

Changes to credits, tariffs, AI settings, broadcasts, or payment state must be auditable at least through timestamps and actor identifiers where practical for the MVP.

## 6. Delivery quality

Keep the AuRoom client-facing MVP simple, but production-safe:

- use migrations for schema changes;
- keep API/service/repository boundaries already used by the project;
- preserve ownership checks;
- add relevant tests for behavior changes;
- run backend tests/integration/migrations and frontend typecheck/build before claiming completion;
- never commit real secrets or customer data;
- do not silently fall back to demo behavior in production.
