# MediMart Production Roadmap

This roadmap separates implemented application behavior from infrastructure and business controls still required for a public healthcare marketplace.

## Launch-Critical

1. Payment reconciliation
   - Add signed Razorpay webhook handling with idempotency keys.
   - Reconcile authorized, captured, failed, refunded, and disputed payments.
   - Move payment and refund changes into an immutable financial event ledger.

2. Private medical media
   - Store prescriptions, seller documents, and support attachments in a private object-storage bucket.
   - Serve files only through short-lived signed URLs after an ownership or staff permission check.
   - Add malware scanning, retention rules, deletion workflows, and access audit logs.

3. Fulfillment and serviceability
   - Add warehouses, serviceable pincodes, courier partners, shipment records, tracking events, and promised delivery windows.
   - Calculate delivery fees and cash-on-delivery eligibility by pincode, weight, seller, and cart value.
   - Use a commercial or self-hosted reverse-geocoding provider for production traffic.

4. Medicine compliance
   - Keep seller-licence evidence collection and named manual compliance review as the controlled production workflow.
   - Add pharmacist review ownership, prescription expiry rules, medicine schedules, quantity limits, substitution controls, and complete review history.
   - Obtain jurisdiction-specific legal, privacy, pharmacy, and medical-device review before public launch.

5. Security and reliability
   - Add rate limiting, account lockout, two-factor authentication for staff, Content Security Policy, secret rotation, structured logs, error monitoring, and uptime alerts.
   - Run automated encrypted backups and regular restore drills.

## High Priority

1. Background jobs
   - Move email, image processing, invoice generation, webhook retries, and scheduled reminders to Celery or an equivalent queue.

2. Order lifecycle
   - Add cancellation windows, partial cancellation, returns, pickup, quality checks, refunds, credit notes, and customer-visible timelines.

3. Seller operations
   - Add bulk CSV import, barcode support, batch and expiry tracking, purchase orders, stock reservations, settlement reports, commissions, and tax invoices.

4. Search and merchandising
   - Move search to PostgreSQL full-text, OpenSearch, or Elasticsearch when catalog scale requires it.
   - Add synonyms, typo tolerance, facets, ranking analytics, sponsored placement controls, and conversion reporting.

5. Customer experience
   - Add delivery estimates before cart, reorder, recurring reminders, verified alternatives, product availability by location, and accessible support escalation.

## Platform Evolution

- Replace application-level aggregate counters with event-driven reporting tables as order volume grows.
- Add API versioning and an OpenAPI contract before mobile apps or third-party integrations.
- Add database replicas, CDN delivery, horizontal application scaling, and blue/green deployments based on measured demand.
- Add data retention, consent records, export/deletion requests, audit evidence, and incident-response procedures.

## Current Foundation

MediMart already includes least-privilege operations roles, seller and business-licence approvals, regulated-product gates, prescription gates, stock locking during checkout, real payment checkout integration, PDF invoices, delivery assignment, notification hooks, detailed geocoded addresses, responsive themes, catalog imagery, database constraints and indexes, focused tests, and whole-site smoke checks.

## Additive 102-Item Delivery Record

This section was appended without removing earlier roadmap commitments. The 102-item scope is now tracked in `ONE_MG_GAP_ANALYSIS.md`; the latest verified status is 24 complete, 14 partial foundations, and 54 planned. The latest additions include lab slot cancellation/rescheduling, delivery OTP/private proof, product trust workflows, and per-user capability overrides.

The remaining work is grouped into four delivery gates: (1) clinical/legal approval and regulated operations, (2) external payment, courier, lab, consultation, storage, and monitoring integrations, (3) finance, fraud, reconciliation, returns, loyalty, subscriptions, and operational queues, and (4) accessibility, localization, performance, observability, backup recovery, and production hardening.

No roadmap item should be marked complete from documentation alone. Completion requires working code, MySQL migration, authorization, user/admin workflow, auditability, automated tests, operational ownership, and external approval where applicable.

## Additive External Readiness Inputs

### Required integrations

- Razorpay live/test keys and webhook secret in `.env`
- Courier API account, documentation, and credentials
- Lab partner API or confirmed manual lab workflow
- Doctor consultation provider or chat/video API
- AI provider API keys and approved models
- Private object storage credentials, such as S3
- SMTP Gmail app password for email notifications
- Production error monitoring and uptime service

### Business decisions

- Delivery pincodes, delivery fees, SLA, COD rules, and return policy
- GST/tax rules and invoice requirements
- Product categories allowed for sale
- Prescription acceptance, pharmacist approval, substitution, and expiry policies
- Cold-chain products and temperature rules
- Refund, cancellation, recall, and reverse-pickup policies
- Loyalty points and Care Plan rules
- Languages to support, beginning with Hindi or Gujarati

### Compliance documents

- Pharmacy and vendor licences
- Pharmacist registrations
- Doctor and lab accreditation records
- Legal review for Drugs and Cosmetics rules, DPDP, GST, consumer protection, and telemedicine
- Privacy policy, consent wording, retention policy, grievance process, and terms

### Production setup

- Domain name and hosting provider
- Dedicated MySQL production user; do not use `root` in production
- Backup destination and restore schedule
- Admin, pharmacist, compliance, delivery, lab, and doctor operational accounts
- Approved production product, vendor, lab, and doctor data

Internal database and workflow delivery can continue without these credentials. Provider-dependent, legal, and production-monitoring work cannot be marked complete until the inputs are supplied.
