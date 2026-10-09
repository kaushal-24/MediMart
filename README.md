# MediMart

MediMart is a Django healthcare marketplace for medicines, medical equipment, prescription-controlled purchases, multi-seller offers, order fulfillment, and role-based operations.

## Capabilities

- Customer accounts, profiles, saved addresses, carts, saved items, reviews, notifications, and support tickets
- Consent-based browser location detection with reverse geocoding, manual pincode fallback, session persistence, and address autofill
- Medicine and medical-equipment catalog with categories, brands, specifications, search suggestions, filters, and seller comparison
- Vendor, pharmacy, and equipment-manufacturer onboarding with approval-controlled catalog and inventory management
- Indian seller-compliance workflow with licence evidence, authorized-registry adapter, official portal fallback, and manual reviewer approval
- Prescription upload and review gates for prescription-required products
- Checkout with coupons, stock locking, cash on delivery, Razorpay checkout, payment verification, invoices, and PDF downloads
- Delivery assignment with controlled fulfillment status transitions and customer notifications
- Customer, vendor/manufacturer, doctor, delivery, and role-scoped management panels
- Custom Operations Center for accounts, catalog, sellers, compliance, orders, prescriptions, coupons, doctors, health guides, support, and notifications
- Django administration remains available at `/admin/` for superusers, alongside the role-scoped Operations Center at `/admin-dashboard/`
- Site-wide light/dark themes and responsive storefront layouts
- MySQL indexes and integrity constraints for common catalog, seller, order, and location queries

## Technology

- Python 3.14
- Django 6.1.1
- MySQL/MariaDB through `mysqlclient`
- Bootstrap 5.3.8 and Bootstrap Icons 1.13.1
- Razorpay 2.0.1
- ReportLab 5.0.1
- Pillow 12.3.0

Install the pinned packages from `requirements.txt`. Production adds Gunicorn through `requirements-production.txt`.

## Local Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py runserver
```

Open `http://127.0.0.1:8000/`.

To rebuild a complete local demonstration database, run:

```powershell
python manage.py reset_demo_data --confirm-reset
```

This command deletes existing MediMart database records before reseeding. Demo logins are documented in `DEMO_CREDENTIALS.md`.

## Configuration

Core settings are read from `.env`:

- `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, and `CSRF_TRUSTED_ORIGINS`
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT`
- SMTP settings for transactional email
- `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, and `RAZORPAY_CURRENCY`
- SMS provider settings
- `GEOCODING_REVERSE_URL`, `GEOCODING_USER_AGENT`, and timeout settings
- Media-storage and HTTPS security settings
- `LICENSE_VERIFICATION_API_URL`, API credentials, timeout, and identification settings for an authorized registry provider

The public OpenStreetMap Nominatim endpoint is suitable only for moderate, user-triggered development use. Commercial deployments should configure a paid or self-hosted provider and preserve attribution.

## Roles

- Customer: shopping, prescriptions, orders, invoices, reviews, addresses, notifications, and support
- Vendor / Pharmacy: business registration, seller offers, stock, sales, and fulfillment visibility
- Manufacturer: equipment catalog submission, offers, inventory, sales, and fulfillment visibility
- Doctor: verified public profile and doctor workspace
- Delivery Staff: assigned deliveries, customer contact, map launch, and controlled status updates
- Compliance Officer: seller and licence verification without unrelated management access
- Catalog Manager: product and seller-offer governance
- Warehouse Manager: stock-risk and fulfillment operations
- Support Staff: customer-ticket access and replies without global administration access
- Operations Manager: cross-functional operations access
- Admin: complete custom Operations Center and searchable record management

## Regulatory Verification

MediMart stores seller licence evidence and can prefill normalized licence data through a configured, documented API. When no authorized API is configured, the workflow links reviewers to the official ONDLS or CDSCO medical-device portal and requires a recorded manual decision. It never treats a portal scrape or an applicant-supplied number as verified.

## Verification

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test tests -v 2
python manage.py smoke_check --use-existing
```

The test suite covers ownership boundaries, prescription gates, checkout and stock behavior, location persistence, seller submissions, admin approvals, delivery assignment and transitions, seller sales reporting, search suggestions, invoices, blog visibility, support privacy, and dark-mode availability.

## Production

Read [DEPLOYMENT.md](DEPLOYMENT.md) and [PRODUCTION_ROADMAP.md](PRODUCTION_ROADMAP.md) before launch. A public healthcare-commerce deployment also needs signed private media delivery, payment webhooks and reconciliation, observability, background jobs, backups with restore drills, legal/privacy review, tax and refund workflows, and provider credentials.

Operational release, scheduler, recovery, and private-file procedures are in [OPERATIONS_RUNBOOK.md](OPERATIONS_RUNBOOK.md).
