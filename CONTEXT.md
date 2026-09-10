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

The approved questionnaire flow is a cumulative visual project rather than a set of unrelated generations.

- The normal `Создать` questionnaire path does not ask the user to choose an existing project. The user selects one or more design objects and presses `Начать проект`; AuRoom creates a new Project automatically with the current questionnaire catalog version and selected-object session, then opens the one-time site source step. Existing-project selection is not part of this flow.
- A Project created by `Начать проект` stays a server-owned hidden questionnaire draft until the one-time site source choice is successfully saved. Hidden drafts never appear in the normal project list. Backing out before that source choice discards the pristine draft immediately; abandoned pristine drafts are automatically soft-deleted after 24 hours, including any project assets uploaded before the source-step save completed. The generic project API cannot set or clear the draft marker.
- Once a generated object is accepted by the user, it is fixed. Adding or regenerating another object must not silently change previously accepted objects. The questionnaire runtime enforces this visually with deterministic masked composition: the user marks the allowed edit rectangle on the accepted scene, accepted lock rectangles have priority, and the worker copies every pixel outside the allowed region (and every protected pixel) from the previous accepted scene into a lossless PNG result.
- The first accepted object (or a legacy accepted object without a lock) must receive a visual lock rectangle before another object can be accepted. Later accepted objects inherit their edit rectangle as a lock, so future generations cannot overwrite those pixels.
- After an object is accepted, the user chooses which object to work on next; the system must not force an automatic next-object order.
- The questionnaire option `Как у дома` is inheritance from the accepted main house. It is hidden and invalid until the main house (`eskez-doma`) has been accepted. Once available, it means the new object should inherit the accepted house's architectural language, including compatible style, materials and roof where the questionnaire supports roof inheritance.
- The existing garage/canopy questionnaire branching remains as approved; do not rewrite it into a new garage-vs-canopy entry question without a separate product decision.
- A completed questionnaire application must be delivered to the administrator in Telegram in addition to being persisted for operator access.

### Questionnaire source-contract invariants

- The site source step is exactly once per questionnaire session: upload a plot photo or explicitly continue without one before any questionnaire answer is accepted. The selected object set and this source choice become immutable once the session starts.
- `Пропустить` is a source-authored action, never a generic optional-question shortcut. It is exposed only when the source defines a default and any source condition for that skip is satisfied.
- `Свой вариант` is an input path, not a literal answer. The client must collect the user's actual value; numeric source bounds are enforced in both client UX and server validation.
- A design object can become accepted only after every active pre-render question has an answer or explicit source-defined skip and the sketch review is positive.
- Accepted object answers are immutable snapshots of the catalog version in which the object was approved. Catalog upgrades must not rewrite or invalidate an already accepted object; unfinished answers are re-evaluated against the new catalog before the next generation/acceptance.
- The application questionnaire is inaccessible until at least one sketch is accepted. A submitted application is persisted and queued for Telegram delivery; deployed runtime readiness requires at least one active admin/superadmin Telegram recipient.
