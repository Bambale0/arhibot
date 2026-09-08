# Canonical house geometry (MVP seam)

AuRoom must not use a generated floor-plan PNG as the source of geometry for the next image model.
The project stores one canonical `architecture` package in `Project.context` and derives technical
representations from that package.

```text
brief/program
    |
    v
ArchitecturePackage
  program + geometry + appearance
          |
          +--> geometry validation
          +--> deterministic floor-plan SVG
          +--> deterministic axonometric massing SVG
          +--> deterministic glTF 2.0 / GLB geometry with explicit facade openings
          +--> immutable ArchitectureRender snapshot + SHA-256 digest
                    |
                    v
              Redis render queue
                    |
                    v
              renderer-worker
                    |
                    v
              Blender headless
                    |
                    v
              geometry-locked PNG hero
```

## Coordinate contract

- Unit: meters.
- X: east/right on plan.
- Y: north/up on plan.
- Z: up.
- Every level uses the same XY world coordinates.
- Exterior corners are explicit polygon vertices.
- Rooms and external objects are explicit polygons, never placement prose.
- A gable roof has explicit ridge endpoints and Z elevations.
- GLB export maps canonical `(x, y, z)` to glTF `(x, z, -y)` so the model stays right-handed and Y-up without changing scale.

## Facade opening contract

Facade openings are value objects inside `LevelGeometry.openings`. They are defined against the
ordered exterior edges of that level's footprint instead of by visual hints or inferred facade
placement.

For a footprint with points `P0, P1, ..., Pn`, exterior edge `0` is `P0 -> P1`, edge `1` is
`P1 -> P2`, and the final edge is `Pn -> P0`. Every opening specifies:

- `id`: stable identifier within the level;
- `kind`: `window`, `door`, or `garage_door`;
- `edge_index`: exterior footprint edge that owns the opening;
- `offset_m`: distance in meters from the start of that directed edge;
- `width_m`: horizontal opening width along the edge;
- `sill_height_m`: opening bottom above the level floor;
- `height_m`: opening height.

Validation rejects openings that reference a missing edge, extend beyond the wall, exceed the level
height, or physically overlap another opening on the same wall. Stacked openings are allowed when
their wall-plane rectangles do not overlap. Doors with a sill above the floor are retained but
reported as warnings so unusual thresholds remain explicit instead of being silently rewritten.

## Project endpoints

- `POST /api/v1/projects/{project_id}/architecture/validate`
- `PUT /api/v1/projects/{project_id}/architecture`
- `GET /api/v1/projects/{project_id}/architecture`
- `GET /api/v1/projects/{project_id}/architecture/plan.svg`
- `GET /api/v1/projects/{project_id}/architecture/massing.svg`
- `GET /api/v1/projects/{project_id}/architecture/model.glb`
- `POST /api/v1/projects/{project_id}/architecture/renders`
- `GET /api/v1/projects/{project_id}/architecture/renders/{render_id}`

The PUT operation rejects invalid geometry before persistence. Deterministic render endpoints read the
saved package directly. An async Blender render instead snapshots the package at enqueue time, stores
a canonical SHA-256 digest, and renders that stored snapshot so later edits cannot silently change an
already queued job.

## Canonical GLB contract

`model.glb` is a real binary glTF 2.0 mesh generated deterministically from the saved package. Levels
and external objects are built in meters; explicit facade openings remove their wall rectangles and
produce separately named window/door meshes; flat roofs are meshed directly; gable roofs use the
explicit ridge; convex hip roofs use a deterministic apex interpretation. The GLB asset metadata
records `source=canonical-geometry`, the schema version, coordinate mapping, opening count and
renderer fidelity warnings.

The exporter does **not** invent window layouts, doors, facade details, decorative elements or
photoreal textures that are absent from `ArchitecturePackage`. Window and door meshes are canonical
surfaces, not a claim that production frames, reveals, hardware or glass assemblies have already been
modeled. Pitched-roof overhangs and roof shapes that cannot be represented faithfully by the current
roof schema are reported as fidelity warnings instead of being silently guessed.

## Blender render job contract

`POST .../architecture/renders` returns `202 Accepted` and creates an `ArchitectureRender` row. The
row is separate from AI `Generation`: it does not select an AI model and does not charge generation
credits. PostgreSQL is authoritative for job state; Redis is the delivery queue. If enqueue delivery
is lost, the renderer worker reconciles queued database rows back into Redis.

The renderer worker builds a canonical GLB from the stored snapshot and runs Blender in a separate
headless process. The current `blender_eevee_v1` profile uses a fixed camera-fitting algorithm,
ground plane, world illumination, sun/key/fill lighting and PNG output. Blender version, dimensions,
status and result URL are persisted with the job. The worker has a render timeout and validates the
PNG before publishing it into the existing media volume.

The dedicated `renderer-worker` container contains the Blender runtime and is intentionally isolated
from the ordinary image-generation worker. Development server smoke tests require this container to
be running, so a deployment with a missing or broken Blender executable cannot silently pass.

## Current MVP boundary

The canonical source now carries footprint/room/external geometry, roof geometry and explicit facade
openings, with deterministic plan SVG, massing SVG, real GLB outputs and an asynchronous Blender hero
render seam. Automated LLM compilation from a natural-language brief, sections, richer production
materials/asset libraries, multiple camera profiles and automatic publication of completed renders
into Ideas remain separate follow-up slices. They must consume the same `ArchitecturePackage` rather
than parse or reconstruct raster images.
