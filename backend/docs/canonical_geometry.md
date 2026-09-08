# Canonical house geometry (MVP seam)

AuRoom must not use a generated floor-plan PNG as the source of geometry for the next image model.
The project stores one canonical `architecture` package in `Project.context` and derives technical
representations from that package.

```text
brief/program
    |
    v
ArchitecturePackage
  program + geometry + appearance/PBR presets
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
              PBR + camera profile
                    |
                    v
              PNG render + deterministic technical QA
                    |
                    +--> single render result
                    |
                    +--> three-angle batch
                           hero_corner
                           reverse_corner
                           elevated
                                |
                                v
                         deterministic winner
                                |
                                v
                         optional Idea publication
                         hero Asset + canonical GLB
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

## PBR appearance contract

`HouseAppearance.pbr_materials` is a strict preset palette. It exists so an LLM or UI can choose a
stable material ID instead of inventing arbitrary shader values. The current preset families are:

- facade: `white_plaster`, `warm_stone`, `red_brick`, `graphite_panel`, `wood_cladding`;
- roof: `dark_metal`, `gray_membrane`, `brown_tile`;
- accent: `natural_oak`, `charcoal`, `warm_stone`, `black_metal`;
- glazing: `clear_glass`, `low_e_glass`, `smoked_glass`.

Legacy descriptive fields such as `primary_material`, `roof_material` and `glazing` remain accepted
for compatibility and human-readable intent. The versioned Blender PBR renderer uses the explicit
preset palette for deterministic shader parameters. Presets currently control base color, metallic,
roughness and, where relevant, alpha/transmission/IOR. They do not claim texture-map, UV or physical
assembly fidelity that the canonical package does not yet contain.

## Project endpoints

- `POST /api/v1/projects/{project_id}/architecture/validate`
- `PUT /api/v1/projects/{project_id}/architecture`
- `GET /api/v1/projects/{project_id}/architecture`
- `GET /api/v1/projects/{project_id}/architecture/plan.svg`
- `GET /api/v1/projects/{project_id}/architecture/massing.svg`
- `GET /api/v1/projects/{project_id}/architecture/model.glb`
- `POST /api/v1/projects/{project_id}/architecture/renders`
- `GET /api/v1/projects/{project_id}/architecture/renders/{render_id}`
- `POST /api/v1/projects/{project_id}/architecture/render-batches`
- `GET /api/v1/projects/{project_id}/architecture/render-batches/{batch_id}`

The PUT operation rejects invalid geometry before persistence. Deterministic render endpoints read the
saved package directly. An async Blender render instead snapshots the package at enqueue time, stores
a canonical SHA-256 digest, and renders that stored snapshot so later edits cannot silently change an
already queued job.

## Admin Idea render endpoints

- `POST /api/v1/admin/ideas/{idea_id}/architecture-render-batches`
- `GET /api/v1/admin/ideas/{idea_id}/architecture-render-batches/{batch_id}`

The admin start endpoint requires an Idea with an `architecture_project_id` owned by the acting
administrator. It creates the same immutable three-angle batch but records the Idea as the publication
target. Backend authorization remains authoritative; public Idea endpoints cannot enqueue or publish
architecture render batches.

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

New jobs use renderer profile `blender_eevee_v2`. The optional request body chooses one of three
versioned camera profiles: `hero_corner` (default), `reverse_corner`, or `elevated`. Camera profile is
persisted with the job so the result is reproducible. A bodyless POST remains valid and selects
`hero_corner` for backward-compatible clients.

`blender_eevee_v2` builds the canonical GLB from the stored snapshot, resolves PBR presets into a
sidecar render config, maps stable canonical mesh names to material roles, and runs Blender in a
separate headless process. It uses a fitted camera, ground plane, world/sun/key/fill lighting,
ambient occlusion where supported, deterministic exposure and 1280x960 PNG output. Blender version,
renderer profile, camera profile, dimensions, status and result URL are persisted with the job.

Every successful Blender PNG becomes a first-class `Asset` with purpose
`architecture_render_output`. The render row stores the Asset id and a deterministic technical-QA
report. Current QA measures luminance, contrast, entropy, edge sharpness and black/white clipping; it
does not reinterpret or alter the architecture.

Existing queued `blender_eevee_v1` rows continue through the legacy rendering path. Snapshot digest
verification hashes the raw immutable JSON stored in PostgreSQL before schema validation, so adding
new default fields to `ArchitecturePackage` cannot invalidate old queued jobs merely because the
application schema evolved.

The dedicated `renderer-worker` container contains the Blender runtime and is intentionally isolated
from the ordinary image-generation worker. Development server smoke tests require this container to
be running, so a deployment with a missing or broken Blender executable cannot silently pass.

## Three-angle batch and winner contract

A render batch creates exactly three jobs from one immutable architecture snapshot:

1. `hero_corner`;
2. `reverse_corner`;
3. `elevated`.

Winner selection is deterministic. Technically usable images outrank unusable images; within the same
usability class the higher QA score wins; an exact score tie uses the camera order above. This logic
is a pure architecture function and does not depend on Redis, Blender, SQL ordering or an AI vision
model.

The worker finalizes a batch only after every member reaches a terminal state. PostgreSQL row locks
make finalization idempotent under concurrent worker completion. Periodic reconciliation also finds
terminal batches that have a completed render but no selected winner, so a process crash between
render completion and publication can recover without rerendering the house.

## Automatic Idea publication safety

A batch created for an Idea may publish the selected render automatically. Publication is allowed
only when all of the following remain true at finalization time:

- the Idea still exists;
- the Idea still points to the same architecture project;
- the project's current normalized canonical architecture digest still equals the batch source digest;
- the selected render passed technical QA;
- its output Asset is present, not deleted, owned by the enqueueing user and attached to the same project;
- the immutable architecture snapshot still validates;
- the canonical GLB stays inside the configured model-size limit.

If any guard fails, the winner remains recorded for diagnostics but the Idea is not overwritten. The
skip reason is written to the admin audit log. This prevents a slow render from replacing a newer
project edit or a deliberately changed Idea source.

On successful publication, the winner Asset becomes the Idea hero, the immutable batch architecture
becomes the Idea architecture snapshot, and a fresh deterministic canonical GLB becomes the Idea 360°
model. Previous model files are removed only after the database commit succeeds. Existing photos,
references and schemes are left untouched.

## Current MVP boundary

The canonical source now carries footprint/room/external geometry, roof geometry, explicit facade
openings and deterministic PBR material presets. AuRoom can derive plan SVG, massing SVG, real GLB,
asynchronous Blender renders, three-angle render batches, deterministic technical QA and guarded
automatic Idea publication from the same source package.

Automated LLM compilation from a natural-language brief, richer texture/asset libraries, semantic
front-facade orientation and optional AI beauty enhancement remain separate follow-up slices. Those
steps must consume the same `ArchitecturePackage` and must not reconstruct or mutate house geometry
from raster images.
