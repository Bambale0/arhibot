# Initial whole-site layout references

Baseline: `382b392`. This follow-up uses the existing canonical initial-concept brief,
visual-fidelity enrichment, signed local media and paid-request checkpoint. It adds
no migration, model name, model routing rule, price or provider setting.

Eligible new requests receive a provider-only, unlabeled ground-plane PNG. The
house polygon occupies the requested ground-area share (total area divided by an
integer floor count). A rectangular pool uses its stated metre dimensions. The
conceptual square is **not** a surveyed cadastral shape. The stored canonical brief
is unchanged.

Eligibility is intentionally bounded: synthetic `whole_site_aerial`, a supported
explicit house polygon and share without layout warnings, separate open rectangular
pools with known dimensions that fit their permitted semantic zone, explicit
full-perimeter hedge/fence, and optionally the
simple lawn-only questionnaire variant. Source photographs, gates, partial boundaries,
other plantings, unsupported objects/shapes/dimensions and fractional attic floor
counts retain the existing generation path. The reference legend names only selected
objects. No labels, measurement lines or unselected fence are drawn.

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
