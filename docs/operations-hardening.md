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

## Public surface and supply chain

Production disables FastAPI Swagger/ReDoc/OpenAPI HTTP routes and the public host Nginx explicitly returns 404 for docs, OpenAPI and metrics. The HTTPS ingress sets HSTS, nosniff, a strict referrer policy, a conservative permissions policy and a Telegram-compatible CSP; Nginx version disclosure is disabled. Deploy applies the canonical host Nginx config with backup, syntax validation, reload verification and rollback on failure.

CI audits Python runtime dependencies with pip-audit and frontend production dependencies with npm audit, builds backend/frontend Docker images, and pins GitHub Actions plus runtime base images to immutable commit/digest identities. Dependabot watches Python, npm, Actions and Docker sources weekly. Python runtime dependencies are still declared as compatible ranges rather than a hash-locked transitive set; producing and maintaining a reproducible lock remains a further supply-chain improvement.

## Still required before a production-grade promotion

- encrypted off-site backups plus periodic isolated restore drills; choose the storage provider from the deployment environment and define RPO/RTO first;
- persistent telemetry storage/dashboards and distributed tracing; the API now exposes internal Prometheus-compatible RED/runtime metrics, while the runtime watchdog covers immediate operational alerts;
- soak/load tests that include authenticated writes and generation-provider latency, not only public read paths;
- blue-green/canary or another zero-downtime release strategy;
- broader controlled failure-injection beyond the Redis pause/recovery CI probe: PostgreSQL outage, provider 429/5xx storms and process-kill recovery in a non-production environment.
