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
- Rotate Razorpay, email, SMS, S3, and field-encryption credentials after suspected compromise.
- Preserve `FIELD_ENCRYPTION_KEY`; losing it makes encrypted payout account numbers unreadable.
- Review the immutable audit trail and payment event ledger before replaying failed operations.
- Use `python manage.py reset_demo_data --confirm-reset` only in local development. It is blocked when `DEBUG=False`.

## Launch Gates

- Authorized Indian licence-registry API contract and manual compliance procedure.
- Pharmacy, prescription, medical-device, tax, privacy, return, and refund legal review.
- Razorpay live account, signed webhook secret, reconciliation owner, and dispute process.
- Transactional email/SMS provider credentials and consent templates.
- S3 lifecycle, malware scanning, backup retention, monitoring, alerting, and restore drill.
