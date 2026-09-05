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
