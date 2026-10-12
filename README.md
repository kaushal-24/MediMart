# MediMart

MediMart is a Django healthcare marketplace for medicines, medical equipment, prescription-controlled purchases, multi-seller offers, order fulfillment, and role-based operations.

## Capabilities

- Customer accounts, profiles, saved addresses, carts, saved items, reviews, notifications, and support tickets
- Consent-based browser location detection with reverse geocoding, manual pincode fallback, session persistence, and address autofill
- Medicine and medical-equipment catalog with categories, brands, specifications, search suggestions, filters, and seller comparison
- Vendor, pharmacy, and equipment-manufacturer onboarding with approval-controlled catalog and inventory management
- Indian seller-compliance workflow with licence evidence and manual reviewer approval
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

MediMart uses a real MySQL database only. Install and run MySQL Server 8.x separately from Django; SQLite is not supported.

Create the local database from the normal MySQL client:

```powershell
mysql -u root -p
```

Then run:

```sql
CREATE DATABASE IF NOT EXISTS medimart CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
EXIT;
```

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
- `CHATBOT_PROVIDER`, `CHATBOT_API_URL`, `CHATBOT_API_KEY`, and `CHATBOT_MODEL`
- SMTP provider settings for outbound email notifications
- `GEOCODING_REVERSE_URL`, `GEOCODING_USER_AGENT`, and timeout settings
- Media-storage and HTTPS security settings

The public OpenStreetMap Nominatim endpoint is suitable only for moderate, user-triggered development use. Commercial deployments should configure a paid or self-hosted provider and preserve attribution.

The assistant supports `gemini` through Gemini's native `generateContent` REST contract and `openai_compatible` providers through `/chat/completions`. Set `CHATBOT_PROVIDER=auto` to detect Gemini from the hostname. The API key remains server-side; the browser only calls MediMart's `/assistant/chat/` endpoint. Seller licences are submitted with evidence and reviewed manually by authorized MediMart staff; no automatic licence-registry API is used.

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

MediMart stores seller licence evidence and requires an authorized compliance officer to record a manual review decision. There is no automatic licence lookup or licence-registry API integration.

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

## Additive Implementation Update

This section was appended without removing or replacing any earlier README content. The complete 102-item healthcare marketplace scope, with honest `[x]`, `[~]`, and `[ ]` status markers, is maintained in `ONE_MG_GAP_ANALYSIS.md`.

The verified current foundation includes MySQL on port 3306, no Redis dependency, pharmacist prescription review, regulated-product controls, batch traceability, cold-chain quarantine, Razorpay webhook/idempotency handling, product variants, moderated product questions and reviews, lab slot cancellation/rescheduling, delivery OTP and private proof capture, per-user capability overrides, private media support, role dashboards, and 111 passing Django tests.

The project is not declared production-complete until legal review, provider contracts, live payment/courier/lab/consultation credentials, object storage, monitoring, backup restore drills, and operational ownership are supplied. Never use the MySQL root account in production; create a dedicated database user and keep all secrets in `.env`.

### Additive single-model AI policy

MediMart currently uses one Groq model only: `openai/gpt-oss-120b`. Keep `CHATBOT_MODELS` set to this single value to avoid unnecessary model calls and fallback usage. The failover code remains available for a future explicit configuration change, but no fallback model is active now.

### Additive Groq AI provider configuration

AI chat and AI catalogue search use Groq's OpenAI-compatible Chat Completions endpoint. Configure `CHATBOT_API_URL=https://api.groq.com/openai/v1`, `CHATBOT_PROVIDER=openai_compatible`, `CHATBOT_API_KEY`, and the comma-separated `CHATBOT_MODELS` fallback list in `.env`. The key remains server-side and is never sent to browser code.

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

Internal database models, workflows, dashboards, admin tools, validation, tests, and UI can be completed without these credentials. External courier, lab, payment, consultation, storage, legal, and production-monitoring features cannot be genuinely production-complete until their providers and policies are supplied.
