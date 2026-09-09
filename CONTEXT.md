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

An admin-managed item in the public authenticated Ideas feed. It can preselect a generation mode and a user prompt when the user starts a generation from the idea.

### Exact 3D model

An Idea may have one operator-uploaded, self-contained glTF 2.0 `.glb` model. This GLB is the only source for an interactive 360° object in the Ideas feed: the client must render the imported mesh/materials and must not synthesize a fake 3D object by wrapping photos around primitive geometry. If no GLB is configured, the feed shows the hero visualization as a non-interactive image. Canonical Architecture geometry remains the source for derived floor-plan schemes, not a substitute for the exact presentation mesh.

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

- Once a generated object is accepted by the user, it is fixed. Adding or regenerating another object must not silently change previously accepted objects. The questionnaire runtime enforces this visually with deterministic masked composition: the user marks the allowed edit rectangle on the accepted scene, accepted lock rectangles have priority, and the worker copies every pixel outside the allowed region (and every protected pixel) from the previous accepted scene into a lossless PNG result.
- The first accepted object (or a legacy accepted object without a lock) must receive a visual lock rectangle before another object can be accepted. Later accepted objects inherit their edit rectangle as a lock, so future generations cannot overwrite those pixels.
- After an object is accepted, the user chooses which object to work on next; the system must not force an automatic next-object order.
- The questionnaire option `Как у дома` is inheritance from the accepted main house. It is hidden and invalid until the main house (`eskez-doma`) has been accepted. Once available, it means the new object should inherit the accepted house's architectural language, including compatible style, materials and roof where the questionnaire supports roof inheritance.
- The existing garage/canopy questionnaire branching remains as approved; do not rewrite it into a new garage-vs-canopy entry question without a separate product decision.
- A completed questionnaire application must be delivered to the administrator in Telegram in addition to being persisted for operator access.
