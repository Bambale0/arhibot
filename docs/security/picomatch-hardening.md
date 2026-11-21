# Arhibot frontend picomatch security hardening (18 November 2026)

The Arhibot frontend uses the unchanged MIT-licensed private NEUROMIX fork
@neuromix/picomatch-hardened@4.0.7+neuromix.1, copied from
Bambale0/banano_kling tanyapi commit 4ae787db41072857f51c28968985d0183075c38f.
It is NOT an official upstream security release. PROVENANCE.json
pins the original npm picomatch 4.0.7 tarball integrity and hashes of all
patched source files. Do not change reviewed bytes without updating provenance
and a separate security review.

This fork rejects +(...) and *(...) repeated extglob syntax before fast paths
and limits patterns to 4096 characters. It is deliberately narrower than
upstream Bash glob semantics. It is a development/build dependency with
repository-owned patterns, not arbitrary user-supplied globs. It does not
guarantee general regex non-backtracking execution.

Reproducible installation: frontend/package.json references the local fork,
overrides.picomatch points to the direct dependency, and install-links=true
ensures correct nested-package resolution. frontend/Dockerfile copies the
vendored source before npm ci.

Mandatory frontend CI retains npm audit --audit-level=high unchanged,
runs npm run security:picomatch first, verifies exact vendor and installed
bytes, runs bounded-execution and ordinary-glob regressions, and additionally
queries advisories for unmodified upstream picomatch 4.0.7. Unknown upstream
advisories or network failure fail closed. Do not hide new advisories or claim
that the official version is patched.

The accompanying Vite upgrade to 8.3.8 addresses separate high-severity
advisories affecting Vite 8.2.2. Require Python pip-audit, Node npm audit,
TypeScript, Vite build, Playwright critical browser E2E, Docker Compose build
and all protected GitHub checks before merging.

Replace the private fork with a verified official patched upstream version
when available, after review and full clean install/test/build validation.
