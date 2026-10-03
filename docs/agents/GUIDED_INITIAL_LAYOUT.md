# Initial whole-site layout references

Baseline: `382b392`. This follow-up uses the existing canonical initial-concept brief,
visual-fidelity enrichment, signed local media and paid-request checkpoint. It adds
no migration, model name, model routing rule, price or provider setting.

Eligible new requests receive a provider-only, unlabeled ground-plane PNG. When
the house has only full storeys, its polygon can carry the requested ground-area
share (total area divided by the integer storey count). When an attic is selected
without an explicit attic-area split, the guide does **not** manufacture a precise
house footprint: the house is only a relative placement anchor and the scale remains
unmeasured. A rectangular or oval pool uses its stated metre dimensions; for a
selected open canopy, the guide additionally encodes the canopy roof projection over
the water footprint. The conceptual square is **not** a surveyed cadastral shape.
The stored canonical brief is unchanged.

Eligibility is intentionally bounded: synthetic `whole_site_aerial`, a supported
explicit house polygon without layout warnings, separate open or canopy-covered
rectangular/oval pools with known dimensions that fit their permitted semantic zone,
explicit full-perimeter hedge/fence, and optionally the simple lawn-only questionnaire
variant. Exact house-area ratios still require full storeys with a measurable ground
share; attic briefs remain placement-only unless sufficient area data exists.
Source photographs, gates, partial boundaries, pool pavilions, attached pools, other
plantings, unsupported objects/shapes/dimensions and other ambiguous geometry retain
the existing generation path. The reference legend names only selected objects. No
labels, measurement lines or unselected fence are drawn.

The worker writes the PNG and commits `initial_layout_guide.v1` before submission
intent. This snapshot retains the file digest, reference role, enriched prompt and
configured model/parameter inputs. Recovery never rebuilds a committed reference or
changes its runtime inputs. Already submitted legacy tasks are not retrofitted.
Unknown submissions remain PROCESSING with their reserved credits and file; accepted
IDs use GET only. Completed output remains recoverable when the temporary PNG has
been lost. A new POST, including fallback after a known failure, requires the original
file and matching digest. Terminal jobs clean up the file; interrupted jobs retain it.

The user-facing generation response exposes only guide version, digest and reference
role. Provider prompts, operator parameters and internal paths remain private.

Evidence: the sanitized fixture `backend/tests/fixtures/initial-layout-case7.json`
preserves the questionnaire values from QA case7 (`07-final-l-house-pool-hedge`,
2026-09-26). Its house is 200m² over two floors on 1,000m² of land; the guide's numeric
ground shares are 10% house and 1.8% pool. Root's live `gpt-image-2` + reference sample
preserved a two-floor L-shaped main volume at approximately 10–12% apparent ground
coverage with no unrequested gate/fence. The same reference with another tested model
did not preserve those constraints. This is a successful sample, not a semantic
acceptance gate or a guarantee for other outputs, catalog changes or configured
models. Operator model changes require fresh visual validation. No paid calls or
runtime configuration changes were made by this implementation task.

Verification covers numerical/raster areas, no text drawing, unsupported-case skips,
the actual QA brief, conditional legends, interruption before submission, accepted
and ambiguous request recovery, runtime changes, missing/tampered input, legacy
checkpoints, credit retention/refund, file cleanup and public response redaction.

Scenario 160 adds a regression for a 1,000m² plot with a 200m² two-storey house plus
attic, an excavated oval 8×4m pool with an open canopy, and a full-perimeter flowering
hedge. Its house footprint is intentionally not certified because the attic-area share
is unknown. The raster regression requires the canopy projection to enclose the pool
water footprint and forbids the hard-fence color in the hedge-only guide.

## Release verification

Local full checks before the final bounded regressions: 413 unit tests and 80
integration tests passed. Final focused coverage: 21 unit tests plus 8 isolated
integration tests passed, including the guided-fallback recovery sequence. Correctness
lint and diff checks passed; independent review found no remaining P1/P2 findings.

All five actual prepared QA sessions (08–12) were checked without provider calls:
minimalism/L, barnhouse/rectangle, Scandinavian/U, classic/square and Mediterranean/L
are eligible. Their house ground shares are respectively 10%, 16.67%, 8.33%, 6.67%
and 9.38%. This eligibility check proves reference construction, not visual adherence
of new provider outputs. The full eligibility report remains in the local audit
artifacts (`guide-eligibility.json`).
