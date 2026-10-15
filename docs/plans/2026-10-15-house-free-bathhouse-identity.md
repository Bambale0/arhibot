# Bathhouse missing when only secondary structures are selected

## Incident diagnosis (2026-10-15)

A finished initial-concept request used `nano-banana-pro` with exactly two
selected objects: `banya` (enclosed Finnish sauna, 30-50 sqm, wood stove with
roof chimney) and `besedka` (gazebo). The user reported a visible
summer-kitchen-like structure instead of the bathhouse.

The canonical prompt **did** contain the sauna's object key, name,
questionnaire constraints, `substitution_forbidden` and a roof chimney
requirement. The model result was not checked by a semantic image judge.

Both selected objects described location relative to a **house that was not
selected** and no source site photo existed. The site plan emitted
`house_relative_constraint_without_house` warnings. That ambiguity weakened
the visual composition contract. The user input was not dropped by the
questionnaire; the generated pixels apparently failed the requested identity.

## Safe correction

For *synthetic-site* initial concepts only:
- Keep the accepted questionnaire and all original answers unchanged.
- Where an object is located relative to a non-existent house, add an
  **approximate**, explicit map to plot-left / plot-right / plot-back /
  plot-front semantic zones; never invent a house.
- Prepend a high-priority instruction making a bathhouse a distinct **enclosed
  building**, not a pergola, gazebo or summer kitchen.
- When the gazebo is also selected, require **two distinct structures**.
  Include the bathhouse roof chimney only if the wood stove was selected.
- Record the list of selected object keys in the provider's
  `visual_acceptance_contract` as an **instruction-only** field (not
  proof of image correctness). Preserve site-photo and house-selected flows.

## Verification and limitations

- Target regression: `pytest -q backend/tests/test_house_free_bathhouse_identity.py`
  (run from backend working directory with `pytest -q tests/test_house_free_bathhouse_identity.py`).
- Full backend/integration/frontend CI must pass before merging.
- No historical user work is silently regenerated or charged.
- Prompt hardening **cannot guarantee** that an image model renders the sauna.
  A future checkpointed Qwen image QA gate should reject a missing or substituted
  selected object before final delivery, without duplicating paid image calls.
- Release gate: `dev` deploys onto a server reporting `APP_ENV=production`.
  Do **not** merge until the operator explicitly approves that impact.
- No video model default is hardcoded here; video selection remains the
  admin-managed runtime setting in PostgreSQL.
