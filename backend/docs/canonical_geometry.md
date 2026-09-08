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
          +--> deterministic glTF 2.0 / GLB massing mesh
          +--> later: facade openings / sections / production Blender scene
          +--> later: photoreal image adapter receives geometry-locked render
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

## Project endpoints

- `POST /api/v1/projects/{project_id}/architecture/validate`
- `PUT /api/v1/projects/{project_id}/architecture`
- `GET /api/v1/projects/{project_id}/architecture`
- `GET /api/v1/projects/{project_id}/architecture/plan.svg`
- `GET /api/v1/projects/{project_id}/architecture/massing.svg`
- `GET /api/v1/projects/{project_id}/architecture/model.glb`

The PUT operation rejects invalid geometry before persistence. Every render endpoint reads the saved
package, so plan, massing and GLB cannot silently come from different house descriptions.

## Canonical GLB contract

`model.glb` is a real binary glTF 2.0 mesh generated deterministically from the saved package. Levels
and external objects are extruded in meters; flat roofs are meshed directly; gable roofs use the
explicit ridge; convex hip roofs use a deterministic apex interpretation. The GLB asset metadata
records `source=canonical-geometry`, the schema version, coordinate mapping and renderer fidelity
warnings.

The exporter does **not** invent facade openings, window layouts, doors, decorative elements or
photoreal textures that are absent from `ArchitecturePackage`. Pitched-roof overhangs and roof shapes
that cannot be represented faithfully by the current roof schema are reported as fidelity warnings
instead of being silently guessed.

## Current MVP boundary

The canonical source now has three deterministic derived representations: plan SVG, massing SVG and a
real GLB massing mesh. This is the stable geometry boundary for the next slices. Automated LLM
compilation from a natural-language brief, explicit facade/opening geometry, sections, Blender-based
PBR materialization, geometry-locked photoreal hero rendering and automatic publication into Ideas
remain separate follow-up slices. They must consume the same `ArchitecturePackage` rather than parse
or reconstruct raster images.
