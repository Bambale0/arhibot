# ADR 0001 — Queue framework: Dramatiq

Status: accepted for the generation/broadcast worker phases.

## Decision

Use Dramatiq with Redis as the first production queue implementation.

## Why

- It is production-oriented and substantially smaller operationally than Celery for this product shape.
- Redis is already part of the platform foundation.
- Actors can remain an infrastructure adapter: API contracts and application services do not import Dramatiq concepts.
- The queue can be replaced later without changing `/api/v1/*` request/response contracts.

## Boundary

Correct dependency direction:

```text
HTTP router -> application service -> repository/provider interface
Dramatiq actor -> application service
```

Forbidden:

```text
application service -> Dramatiq actor
API response model -> Dramatiq message
```

The actual broker/worker wiring is intentionally deferred to Phase 5, where generations are introduced.
