# MediMart Operations Runbook

## Release

1. Back up MySQL and verify the backup can be read.
2. Install `requirements.txt` in a fresh virtual environment.
3. Load production variables from `.env.production.example` using real secrets.
4. Run `python manage.py check --deploy` and resolve every warning.
5. Run `python manage.py migrate --plan`, then `python manage.py migrate --noinput`.
6. Run `python manage.py collectstatic --noinput`.
7. Restart the application workers and verify `/health/live/` and `/health/ready/`.
8. Complete one low-value Razorpay test order, webhook receipt, invoice download, cancellation, and refund.

## Scheduled Jobs

Run these through Windows Task Scheduler, systemd timers, or the deployment platform scheduler. Do not run overlapping copies.

```powershell
python manage.py release_expired_reservations
python manage.py process_notification_queue --limit 200
python manage.py process_refunds --limit 50
```

Recommended cadence: reservations every 5 minutes, notifications every minute, refunds every 5 minutes.

## Private Files

For an existing local installation, run this once after migration:

```powershell
python manage.py migrate_private_media
```

The command copies legacy regulated files into `private_media` and leaves the source intact. Confirm secure downloads work, back up both locations, and remove legacy public copies through an approved maintenance procedure. Cloud transfers must place regulated prefixes under the private S3 location and must never make that prefix public.

## Recovery

- Restore MySQL and private media from the same recovery point.
- Rotate Razorpay, email, S3, and field-encryption credentials after suspected compromise.
- Preserve `FIELD_ENCRYPTION_KEY`; losing it makes encrypted payout account numbers unreadable.
- Review the immutable audit trail and payment event ledger before replaying failed operations.
- Use `python manage.py reset_demo_data --confirm-reset` only in local development. It is blocked when `DEBUG=False`.

## Launch Gates

- Manual Indian licence evidence and compliance review procedure.
- Pharmacy, prescription, medical-device, tax, privacy, return, and refund legal review.
- Razorpay live account, signed webhook secret, reconciliation owner, and dispute process.
- Transactional email provider credentials and consent templates.
- S3 lifecycle, malware scanning, backup retention, monitoring, alerting, and restore drill.

## Additive 102-Item Operations Update

This section is appended to the existing runbook. Use `ONE_MG_GAP_ANALYSIS.md` as the release checklist and keep the following ownership gates visible:

- Pharmacy and pharmacist owners approve prescription, substitution, controlled-product, recall, cold-chain, and dispensing workflows.
- Clinical and lab owners approve doctor, phlebotomy, sample-chain, structured-report, abnormal-result, and non-diagnostic explanation workflows.
- Finance owners reconcile Razorpay webhook events, refunds, settlements, chargebacks, COD collections, invoices, and ledger exceptions.
- Delivery owners manage assignment, OTP verification, proof of delivery, courier events, NDR/RTO, reverse pickup, and SLA escalation.
- Privacy and security owners manage consent, private media, AI redaction, access logs, retention, deletion, incident response, secret rotation, and restore drills.
- Product and accessibility owners verify loading, empty, error, offline, mobile, keyboard, contrast, reduced-motion, and responsive-image states.

Do not accept a checklist item as complete until its workflow has an owner, database state, authorization rule, admin or operational action, audit trail, tests, and any required external or legal approval.

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

Internal workflows may be developed without these credentials. External providers, legal approvals, and production monitoring remain launch prerequisites.
