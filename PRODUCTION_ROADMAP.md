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
   - Connect the implemented seller-licence adapter only after receiving documented regulator/provider API access; keep manual review as the controlled fallback.
   - Add pharmacist review ownership, prescription expiry rules, medicine schedules, quantity limits, substitution controls, and complete review history.
   - Obtain jurisdiction-specific legal, privacy, pharmacy, and medical-device review before public launch.

5. Security and reliability
   - Add rate limiting, account lockout, two-factor authentication for staff, Content Security Policy, secret rotation, structured logs, error monitoring, and uptime alerts.
   - Run automated encrypted backups and regular restore drills.

## High Priority

1. Background jobs
   - Move email, SMS, image processing, invoice generation, webhook retries, and scheduled reminders to Celery or an equivalent queue.

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
