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
          +--> later: elevations / sections / 3D mesh
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

## Project endpoints

- `POST /api/v1/projects/{project_id}/architecture/validate`
- `PUT /api/v1/projects/{project_id}/architecture`
- `GET /api/v1/projects/{project_id}/architecture`
- `GET /api/v1/projects/{project_id}/architecture/plan.svg`
- `GET /api/v1/projects/{project_id}/architecture/massing.svg`

The PUT operation rejects invalid geometry before persistence. The render endpoints always read the
saved package, so plan and massing cannot silently come from different house descriptions.

## Current MVP boundary

This change establishes the geometry source of truth and deterministic render seam. Automated
LLM compilation from a natural-language brief, facade/opening generation, sections, export to a real
3D exchange format and photoreal materialization are intentionally next slices. They should consume
this same interface rather than parsing raster plans.
