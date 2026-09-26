# AuRoom operations hardening

This runbook covers the internet-facing AuRoom development runtime. It does not contain secret values.

## Production runtime preflight

`ops/deploy_docker.sh` validates `backend/.env` before changing application files, containers, or the database. The public runtime must have:

- `APP_ENV=production`;
- independent high-entropy `JWT_SECRET`, `REFRESH_TOKEN_SECRET`, and `MEDIA_SIGNING_SECRET`, each at least 32 characters;
- HTTPS `MEDIA_PUBLIC_BASE_URL`, `NEXUS_BASE_URL`, and `TELEGRAM_WEBAPP_URL` when configured;
- no `localhost` or `127.0.0.1` origins in `CORS_ORIGINS`;
- a runtime `.env` that is not group/world-readable (normally mode `0600`).

Generate secret values outside Git and never print them to CI logs. Rotating `JWT_SECRET` and `REFRESH_TOKEN_SECRET` invalidates current browser/Telegram Mini App sessions and must be treated as an explicit maintenance action.

A read-only preflight can be run with:

```bash
python3 ops/runtime_preflight.py backend/.env
```

## Private media links

Raw `/uploads/...` access is disabled. API responses expose short-lived HMAC-signed `/api/v1/media/...` links instead. The generation worker gives Nexus a signed reference URL long enough for the configured generation deadline. Signed query parameters are excluded from both the canonical host Nginx media location and the container Nginx media location; the application access log records only the path. Apply `backend/deploy/nginx-archibot.conf` to the host Nginx as part of the controlled runtime-hardening maintenance before relying on log secrecy. Use `ops/install_host_nginx.sh /root/arhibot /etc/nginx/sites-available/archibot.xn--e1aikcel5c5a.online CHECK` for a read-only comparison and replace `CHECK` with `APPLY` only after operator approval; the script backs up the old site, validates `nginx -t`, and restores it if validation fails.

A previously issued media link can remain usable until its short expiry even if the asset is soft-deleted. After expiry it cannot be refreshed without going through an authorized application endpoint or a new public Ideas response.

## Release identity and database recovery

Every application container carries the `com.auroom.release` label. After a successful deploy, `.release/current.env` records the release SHA, Alembic version, deployment timestamp, code backup, and pre-migration runtime backup. Server smoke checks verify container/release parity.

If a deploy fails before migrations complete, the deploy script may restore the previous code automatically. If a migration has completed, automatic old-code rollback is intentionally suppressed because old code against a new schema can be unsafe. The deploy log prints the exact runtime backup that can be restored after operator approval.

`ops/restore_runtime.sh ... RESTORE` is destructive and requires explicit operator approval. After restoring the database and media, it migrates the restored database forward to the code currently installed on disk before bringing the stack back up.

Before relying on a snapshot, run the non-destructive isolated restore drill:

```bash
bash ops/verify_restore_isolated.sh /root/arhibot /root/arhibot/backups/runtime/<snapshot>
```

The drill verifies checksums and the media archive, restores `postgres.dump` into an ephemeral PostgreSQL container with no host port or production volume attached, runs the currently deployed API image's Alembic migrations to head, checks the migrated revision, prints safe row-count diagnostics, and removes the temporary container when finished. It does not stop production services, connect to the live database, or overwrite live media.

This drill proves that the local artifact is restorable. It is not an off-site durability guarantee. Off-site export requires host-only `.backup.env` and `age`, using either the Telegram transport described below or an rclone remote with `AUROOM_OFFSITE_BACKUP_REMOTE` and `AUROOM_BACKUP_AGE_RECIPIENT`. Provider credentials and the age private identity must never be committed to the repository or injected into application containers.

## Disk steady state

Deploy refuses to start at 90% filesystem usage and warns at 80%. `ops/runtime_housekeeping.sh` is read-only by default:

```bash
./ops/runtime_housekeeping.sh /root/arhibot REPORT
```

`APPLY` deletes expired release workdirs and prunes dangling Docker images plus unused builder cache. A successful deploy runs `APPLY` after the rollout has already passed health gates; cleanup failure is reported but does not roll back a healthy release. `REPORT` remains available for read-only inspection.

Runtime DB/media backups keep their existing database-managed retention. Release workdir and Docker cleanup are separate from backup retention.

## 3D renderer

The 3D renderer is intentionally disabled while the product does not expose 3D. `renderer-worker` is behind the Compose `3d` profile, regular deploys keep it stopped, and server smoke fails if it is unexpectedly running. Re-enabling 3D requires a separate product/release decision and validation of its deploy parity and capacity budget.

## Runtime guardrails and monitor

Compose applies environment-overridable CPU, memory, PID and json-file log-rotation budgets to every active AuRoom service; the disabled 3D renderer remains outside this capacity claim until it is explicitly re-enabled and re-sized. The initial defaults were chosen after a live read-only pre-production baseline: the API stayed below 100 MiB during a 20-concurrent request burst, while the generation worker retains a much larger memory budget for image decoding/composition. Re-measure before materially increasing traffic or image limits.

`ops/runtime_monitor.sh` runs from root cron every 15 minutes. It checks HTTP readiness, release SHA parity, Docker health, worker heartbeats, stale processing generations, filesystem usage and runtime-backup age. State transitions to WARN/FAIL and recovery back to OK are sent once to active Telegram admins; unchanged state is not re-sent every cycle. Thresholds are environment-overridable.

### Bounded authenticated load probe

`backend/scripts/http_load_probe.py` measures concurrent authenticated HTTP traffic against an API v1 endpoint and reports throughput, error rate and p50/p95/p99 latency. Read mode calls only `GET /me`; `project-write` mode creates temporary Projects and immediately soft-deletes them. It never starts Generations, payments, broadcasts or provider calls.

The probe refuses non-loopback targets by default. A remote read requires `--allow-remote`; remote Project writes require both `--allow-remote` and `--allow-remote-writes`. Supply the bearer token through `AUROOM_LOAD_TOKEN`, not a command-line argument, so it is not exposed in process listings or shell history.

CI runs the probe over a real Uvicorn TCP listener with a disposable authenticated user for both read traffic and reversible Project writes. This is a bounded regression gate, not a long-duration capacity certification. Provider-backed soak testing remains a separate staging exercise because it consumes external AI capacity and can incur provider cost.

### Controlled crash and dependency failure probes

Backend integration CI deliberately pauses and resumes isolated Redis/PostgreSQL instances, then verifies bounded failure detection and recovery through the application's real client paths. It also SIGKILLs a worker process that owns the production singleton lease/heartbeat primitives, verifies a replacement cannot overlap while the stale lease is alive, waits for lease expiry, and proves a clean replacement becomes healthy. Provider resilience tests simulate sustained HTTP 429/5xx storms and assert retry counts remain bounded and the shared circuit breaker opens rather than hammering the dependency.

## Public surface and supply chain

Production disables FastAPI Swagger/ReDoc/OpenAPI HTTP routes and the public host Nginx explicitly returns 404 for docs, OpenAPI and metrics. The HTTPS ingress sets HSTS, nosniff, a strict referrer policy, a conservative permissions policy and a Telegram-compatible CSP; Nginx version disclosure is disabled. Deploy applies the canonical host Nginx config with backup, syntax validation, reload verification and rollback on failure.

CI audits the hash-locked Python runtime dependency set with pip-audit and frontend runtime and development dependencies with npm audit, builds backend/frontend Docker images, and pins GitHub Actions plus runtime base images to immutable commit/digest identities. Dependabot watches Python, npm, Actions and Docker sources weekly. `backend/requirements.lock` and `backend/requirements-build.lock` are generated deterministically with pip-tools from `pyproject.toml`; CI regenerates both and fails on drift. The wheel builder installs only the hash-locked build graph and runs with `--no-build-isolation`; production runtime stages install only the hash-locked runtime graph, then install the already-built AuRoom wheel with `--no-deps`. A Docker build therefore cannot silently resolve a different runtime or Python build dependency graph.

To update the Python locks after an intentional dependency change, install backend dev dependencies and run `./scripts/dependency_locks.sh UPDATE` from `backend/`. Use `CHECK` for a read-only freshness verification; CI runs exactly that mode.

## Still required before a production-grade promotion

- encrypted off-site backups are a mandatory release gate; Telegram export and independent restore were verified on 2026-09-22 (see the dated readiness report); maintain operator key custody and the documented recovery policy;
- persistent telemetry storage/dashboards and distributed tracing; the API now exposes internal Prometheus-compatible RED/runtime metrics, while the runtime watchdog covers immediate operational alerts;
- long-duration soak/capacity testing with generation-provider latency is still required in staging; CI now has a bounded authenticated TCP load gate covering reads and reversible Project writes without external provider cost;
- blue-green/canary or another zero-downtime release strategy;
- controlled failure-injection now covers Redis/PostgreSQL pause-recovery, worker SIGKILL singleton/heartbeat recovery, and sustained simulated provider 429/5xx storms; continue extending these probes when new stateful workers or providers are introduced.

## Encrypted Telegram off-site backups

The alternative to rclone is `AUROOM_BACKUP_TRANSPORT=telegram` in host-only `.backup.env` (0600), with `AUROOM_BACKUP_AGE_RECIPIENT` containing an age **public** recipient. Install `age` on the host. The private age identity must stay with the operator, outside the application server and Telegram backup chat.

The transport uses the existing bot token and active admin/superadmin Telegram identities from PostgreSQL. Optional `AUROOM_BACKUP_TELEGRAM_RECIPIENT_IDS` selects private administrator chats; it never overrides DB role checks. Each selected administrator must have started the bot. Group chats are deliberately not accepted by this admin-only transport.

The archive is encrypted before leaving the host and split into 19,000,000-byte chunks, below the cloud Bot API download limit. Upload progress persists per part/recipient. Every encrypted part and the manifest are downloaded and hashed before `OFFSITE_OK` is written. A lost send response can produce a duplicate document, but ordered part names and manifest hashes make recovery unambiguous. Partial delivery never marks the snapshot successful. See the [Telegram file API](https://core.telegram.org/bots/api#getfile).

New snapshots use manifest v2: the current database/checksums and media are encrypted as separate components. If a previously verified snapshot has exactly the same media SHA-256 and age recipient, its already delivered media parts are reused. The current manifest embeds every required part name, size, hash and Telegram file ID directly, including legacy v1 full-bundle parts when upgrading; it does not depend on an older manifest or local snapshot directory. Reused parts are downloaded and checked again for the new snapshot, with resumable progress. With unchanged media, administrators normally receive only one small database part and one manifest instead of the full media archive at every deploy. Changed media still requires a new full media upload.

Keep all Telegram parts referenced by the current manifest, even when their filenames contain an older snapshot date. Local retention can remove old snapshot folders without breaking recovery. For manual recovery, gather the referenced older media parts and current database parts into the same `--parts-dir`. The recovery command supports both v1 and v2; when media comes from a legacy full bundle it extracts only `media.tar.gz`, preserving the current database/checksums. Incomplete v1 exports continue with their original format. Encryption, administrator selection, scheduling, retention, fresh pre-migration snapshots and the mandatory off-site gate are unchanged.

```bash
# Export or resume a verified snapshot to selected administrators.
python3 ops/telegram_backup.py export /path/20260922T120000Z --app-dir /root/arhibot

# On a separate recovery machine, save the manifest and all parts from Telegram.
# --parts-dir needs no bot token; target must be empty.
python3 ops/telegram_backup.py recover /safe/snapshot.manifest.json \
  --parts-dir /safe/downloaded-parts --identity /safe/private.agekey --target /safe/recovered

# Or retrieve chunks via the original bot's token supplied through environment/secret storage.
python3 ops/telegram_backup.py recover /safe/snapshot.manifest.json \
  --identity /safe/private.agekey --target /safe/recovered

# Validate checksums after relocation, including historical absolute-path manifests.
python3 ops/backup_manifest.py verify /safe/recovered
```

Use `verify_restore_isolated.sh` against the recovered directory before any real restore. `backup_readiness.py` prevents an existing-runtime deployment without a verified off-site snapshot. Backup cadence/retention remain database-managed; backup destination and encryption material are host infrastructure configuration. Backend images run as UID/GID 10001; deployment changes existing media volume ownership only after writers stop, and restore extracts files as that user.
