# Visual release verification — 30 September 2026

Baseline: dev0a7aaa9. Historical paid review found content errors even when the queue,
credit ledger, provider delivery and edit pixel protection worked. A completed task
is not proof of architectural fidelity.

## Changes

The existing provider-only adapter now separates full above-ground storeys from an
additional attic, basement and double-height room for all selected footprints and
both initial source modes. Explicit gable roofs require gable ends. Visible facade
finishes retain their selected order and take priority over underlying structural
wall material; planken means boards, not exposed logs. Chimney requirements are
scoped separately to the house and bath, including explicit negative selections.

An excavated pool is at ground/deck level. Its selected canopy covers the water;
a pavilion encloses the basin, and an open pool remains uncovered. An oval is not
a rounded rectangle. These rules apply to initial scenes and newly added objects,
not to later refinements/removals that may deliberately change old answers. The
canonical stored brief remains unchanged. Synthetic scenes without a selected
fence/gate must not invent entrance structures to make plot boundaries readable;
existing source-photo context is preserved.

No migration, runtime policy, model, retry allowance, tariff, credentials or API
contract changes. Rollback uses a normal revert PR to dev. Existing paid requests
retain their committed provider checkpoints. Do not redeploy while a paid acceptance
job is active.

## Release criteria still requiring evidence

- New image compliance: selected full storeys/attic, roof, cladding, pool cover and
  absent unrequested fences/chimneys/text must be checked on actual provider output.
- The pixel gate verifies outside-region integrity and seams only. It does not
  detect semantic errors. The current provider's public OpenAPI schema explicitly
  states that `/v1/chat/completions` rejects `image_url`/`input_image` with422
  (checked30September at https://nexusapi.dev/openapi.json). No unsupported vision
  call, hidden purchase or invented judge has been added.
- OCR alone is insufficient: a local Tesseract trial on the rejected historical
  scene produced high-confidence punctuation on landscaping. It must not be wired
  to paid automatic regeneration without demonstrated precision/recall.
- Generated orbit frames still have no shared reconstructed geometry. Prompting
  independently generated views does not guarantee a coherent camera path.
  The separate canonical GLB/Blender workflow needs explicit geometry and is not
  a faithful reconstruction of an arbitrary generated photograph.
- A normalized reference ground plan does not certify the scale in a perspective
  output. Exact metric validation requires known camera/geometry correspondence.

Do not mark these criteria satisfied merely because code/CI/deployment is green.
No production promotion is part of this change. Acceptance spending remains inside
the cumulative300RUB cap, with294.80RUB already settled at baseline.
