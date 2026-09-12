# AuRoom domain context

## Control Plane

The authenticated web admin used by operators to manage business configuration and operational entities without changing code, SQL, shell commands, or environment files.

## Business Configuration

Data expected to change during normal product operation. It lives in PostgreSQL and is managed through the Control Plane. Current examples: tariffs, idea feed content, generation model selection and parameters, prompt templates, user credit adjustments, broadcasts.

## Secret Configuration

Credentials or cryptographic material required to connect infrastructure/providers. Secrets do not belong in the Control Plane and must not be exposed to the browser or stored as plaintext business settings. Examples: Nexus API key, YooKassa secret key, Telegram bot token, JWT secrets.

## Tariff

An admin-managed purchasable credit package. It has an immutable machine `code`, human name/description, credit quantity, price/currency, active state and ordering. A payment snapshots tariff values at payment creation so later tariff edits do not rewrite payment history.

## Credit

The AuRoom usage balance attached to a user. Credits can be increased by successful payments or audited admin adjustments. Admin adjustments may not make the balance negative.

## Generation Runtime Settings

The admin-managed primary model, optional fallback model, provider parameters and per-generation-mode parameters used by the worker. Provider credentials are separate Secret Configuration.

## Prompt Template

An admin-managed prompt body for one generation mode. The stable placeholders are `{project_context}` and `{user_prompt}`. Generation modes themselves are API/domain contract values, not business configuration.

## Idea

An Idea is a user-published accepted work created through the normal `Создать` questionnaire flow. The Ideas feed is a showcase of real generated results, not a second generation editor.

- A publication references one completed Generation that was accepted into its Project questionnaire session.
- The publication stores a presentation snapshot of the accepted questionnaire object names and user-facing question/answer pairs so later display-copy changes do not mutate the published card.
- Questionnaire catalog revisions are preserved in the database. Publishing an older accepted work resolves its exact historical catalog revision, so normal admin-managed catalog evolution does not require code-level compatibility tuples.
- The generated output asset is the hero image. Ideas do not own a separate prompt, manually uploaded hero, media carousel, or presentation-only GLB.
- `Создать похожее` starts a fresh questionnaire Project with the same selected object set, then follows the same source step, questions, validation, generation and acceptance rules as normal `Создать`. It does not copy the original user's answers into the new project.
- The owner explicitly adds an accepted generated work to Ideas from the Create flow. This action is the publication consent; another user cannot publish the generation by id.
- Only pre-render design answers are included in the presentation snapshot; application/contact answers are never exposed in the feed.
- Web admin does not create publications. It can moderate visibility and ordering. Hiding a publication removes it from the public feed without deleting the source Project or Generation.
- Interactive 3D is intentionally disabled for the current Ideas release. The feed renders the generated output as a static image only; dormant legacy 3D code is not imported into the feed bundle.

## Broadcast Campaign

An admin-created Telegram message with lifecycle/status and delivery counters. Sending is an explicit operator action and is recorded in the audit log.

## Admin Audit Log

Append-only operational trace of admin changes such as tariff edits, AI configuration changes, credit adjustments, payment reconciliation and broadcast sending.

## Generation Price

The admin-managed number of Credits reserved when a user starts one Generation of a specific mode. A disabled or missing price makes that mode unavailable for paid generation until an operator configures it.

## Credit Transaction

An immutable balance movement that records why Credits changed, the resulting balance, and the related business object when one exists. Payment credits, Generation reserves/refunds, refund debits/rollbacks, and admin adjustments are represented as Credit Transactions and must be idempotent where an external or retryable action is involved.

## Payment Refund

A full reversal of a successful YooKassa Payment. AuRoom reserves the purchased Credits before requesting the provider refund, rolls that reservation back if the provider rejects or cancels the refund, and marks the Payment refunded only after YooKassa confirms success.

## Billing Settings

Admin-managed fiscal behavior for YooKassa receipts, such as whether receipts are enabled and the configured VAT/payment classifications. Provider credentials remain Secret Configuration.

## Broadcast Delivery

The per-recipient delivery state for one Broadcast Campaign. Delivery attempts are retryable and rate-limit aware; a Campaign is terminal only when no pending, retrying, or sending deliveries remain.

## Operational Settings

Admin-managed runtime protections and lifecycle settings such as rate limits, media retention, backup cadence, and backup retention. These are operational controls, not Secret Configuration.

## Telegram Content

The public non-secret bot copy managed through the Control Plane: bot name, descriptions, `/start` welcome text, Mini App button text and command descriptions. The Telegram token remains Secret Configuration. The bot periodically refreshes Telegram Content from the AuRoom API so copy changes do not require a release.

## Questionnaire Project Flow

The approved `Создать` flow has two explicit phases: one initial whole-site concept, then isolated paid refinements.

- The user selects one or more design objects before project launch. `Начать проект` creates a new questionnaire Project with that exact ordered selection and the current catalog revision; existing-project selection is not part of the normal flow.
- A new Project remains a server-owned hidden draft until the one-time site source choice is saved. Backing out before that choice discards the pristine draft; abandoned pristine drafts are soft-deleted by maintenance.
- **Initial concept:** AuRoom collects every active pre-render answer for every object selected before launch. No AI generation is started while those questionnaires are being filled. When all selected questionnaires are complete, one server-built `AUROOM_INITIAL_CONCEPT_V1` request creates one Generation and therefore one credit reservation according to the admin-managed `master_plan` price.
- The initial render is a single coherent site composition. All selected objects must be visible simultaneously. Its camera is a high-angle oblique aerial view at 50–70 m with the whole plot readable. A user-uploaded site photo supplies site geometry, boundaries and environmental context; its original camera angle does not lock the initial render.
- Before the initial Generation is accepted, questionnaire answers remain editable. Changing an upstream answer must remove dependent answers that became inactive or invalid before another Generation can be requested.
- Accepting the initial concept atomically snapshots the selected object set onto the accepted scene. Historical questionnaire projects created before `initial_concept_mode` keep the previous per-object lifecycle for compatibility.
- **Refinement:** after the initial concept is accepted, changing, adding, or removing an object is a new Generation. The user selects the object/action and marks the exact edit rectangle. Changes include a requested edit description; removal uses an explicit remove-object prompt that reconstructs only the selected background area. Every iteration uses the last accepted scene, preserves its camera, and uses deterministic masked composition; every pixel outside the allowed edit rectangle is restored from the accepted input scene.
- Removing an accepted object is never a metadata-only delete. The object remains accepted until the masked removal Generation completes and the user accepts that visual result. Only then is it moved to the session's removed-object history and the new output becomes the accepted scene. The final remaining accepted object cannot be removed from this flow.
- A completed questionnaire application is available only after an accepted scene and is persisted plus delivered to configured administrators in Telegram.
- The existing garage/canopy questionnaire branching remains source-authored. Do not replace it with a new entry question without a separate product decision.

### Questionnaire source-contract invariants

- The site source step occurs exactly once before any questionnaire answer is accepted.
- The object set selected before the initial concept is the complete input to that one whole-site Generation.
- `Пропустить` is source-authored and appears only when its explicit default and condition allow it.
- `Свой вариант` is an input path, never a literal stored answer. Numeric bounds are enforced in client and server validation.
- Active option dependencies are authoritative in both client and server. For example, floor-specific terrace/balcony options cannot refer to a storey the selected house configuration does not have.
- Until the initial concept is accepted, users can navigate backward and revise answers. Dependent answers invalidated by a revision are discarded rather than silently retained.
- After acceptance, the accepted scene is immutable except through an explicit paid masked refinement. A submitted application is persisted and queued for Telegram delivery.
