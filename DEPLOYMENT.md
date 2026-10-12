# MediMart Deployment Guide

This guide shows a simple VPS deployment for MediMart using Django, MySQL, Gunicorn, Nginx, and HTTPS.

## 1. Server Packages

On Ubuntu, install the system packages:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-dev build-essential pkg-config default-libmysqlclient-dev mysql-server nginx certbot python3-certbot-nginx
```

## 2. Project Folder

Copy or clone MediMart to the server:

```bash
sudo mkdir -p /var/www/MediMart
sudo chown -R $USER:www-data /var/www/MediMart
cd /var/www/MediMart
```

Create the virtual environment and install production dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-production.txt
```

## 3. Environment File

Create `.env` from `.env.production.example`:

```bash
cp .env.production.example .env
```

Update at least:

- `SECRET_KEY`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- Email settings if password reset or support email will be used
- `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`
- SMTP provider URL and credentials if outbound notification email is enabled
- A production geocoding endpoint and contactable `GEOCODING_USER_AGENT`
- Cloud object storage settings for uploaded prescriptions, documents, and images

When `USE_CLOUD_MEDIA=True`, MediMart uses the S3-compatible storage backend from
`django-storages`. Configure `MEDIA_CLOUD_BUCKET`, the AWS credentials, and the
region. Set `AWS_S3_ENDPOINT_URL` only when using a compatible provider rather
than AWS S3. Uploaded files remain private and are served through expiring signed
URLs; keep bucket-level public access disabled.

MediMart does not scrape or call government licence portals. Applicants submit licence
details and evidence, and compliance officers complete the review manually. Keep the
reviewer decision and supporting document as auditable evidence, subject to your
retention policy.

For production, keep:

```env
DEBUG=False
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
USE_X_FORWARDED_PROTO=True
```

## 4. MySQL Database

Create a production database and user:

```sql
CREATE DATABASE medimart_prod CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'medimart_user'@'localhost' IDENTIFIED BY 'replace-with-a-strong-database-password';
GRANT ALL PRIVILEGES ON medimart_prod.* TO 'medimart_user'@'localhost';
FLUSH PRIVILEGES;
```

Then run:

```bash
python manage.py migrate
python manage.py collectstatic
python manage.py createsuperuser
```

Optional demo data:

```bash
python manage.py seed_products
python manage.py seed_vendors
python manage.py seed_coupons
```

## 5. Gunicorn

Copy the example service and edit paths/user if needed:

```bash
sudo cp deployment/gunicorn.service.example /etc/systemd/system/medimart.service
sudo systemctl daemon-reload
sudo systemctl enable medimart
sudo systemctl start medimart
sudo systemctl status medimart
```

## 6. Nginx

Copy the Nginx example:

```bash
sudo cp deployment/nginx.conf.example /etc/nginx/sites-available/medimart
sudo ln -s /etc/nginx/sites-available/medimart /etc/nginx/sites-enabled/medimart
sudo nginx -t
sudo systemctl reload nginx
```

Replace `medimart.example.com` in the config with your real domain.

## 7. HTTPS

After DNS points to the server, issue an HTTPS certificate:

```bash
sudo certbot --nginx -d medimart.example.com -d www.medimart.example.com
```

## 8. Deployment Check

Run Django's deployment checks:

```bash
python manage.py check --deploy
```

Warnings about HSTS preload are normal unless you intentionally join the browser preload list. Review every other warning before public launch.

## 9. Updating The Site

For later updates:

```bash
cd /var/www/MediMart
source .venv/bin/activate
pip install -r requirements-production.txt
python manage.py migrate
python manage.py collectstatic
sudo systemctl restart medimart
```

## 10. Production Notes

- Keep `.env` private and never commit it.
- Back up the MySQL database and either `media/` uploads or the configured object-storage bucket.
- Keep prescription and vendor-document uploads private; serve them through authorized views or signed object-storage URLs.
- Use a paid or self-hosted reverse-geocoding service at commercial traffic levels. The public OpenStreetMap Nominatim service has strict usage and attribution requirements.
- Configure payment webhooks before accepting live Razorpay payments; browser callbacks alone are not sufficient for final payment reconciliation.
- Do not auto-approve regulated sellers from applicant-entered data. Validate licence scope, premises, status, validity dates, and product category through an authorized source, then retain a named reviewer decision.
- Run scheduled database backups and perform restore drills.
- Add application error monitoring, uptime checks, structured logs, and alerting before launch.
- Serve `staticfiles/` from Nginx. In local-filesystem deployments, serve authorized media carefully; cloud deployments use signed object-storage URLs.
- Keep `DEBUG=False` on public servers.
- Keep the development server for local work only; production should use Gunicorn behind Nginx.

## Additive 102-Item Readiness Record

This section is additive and does not replace any deployment instruction above. Before treating the full MediMart scope as production-ready, complete the checklist in `ONE_MG_GAP_ANALYSIS.md` and obtain evidence for each external dependency.

Required launch inputs are a production domain and HTTPS certificate, dedicated MySQL credentials, live Razorpay keys and signed webhook secret, transactional SMTP credentials, private object storage with signed URLs, malware scanning, courier and lab partner accounts, doctor consultation provider access, approved AI provider configuration, error monitoring, uptime alerts, backup storage, restore-drill evidence, and named owners for pharmacy, clinical, finance, delivery, support, privacy, and incident response.

Healthcare legal and regulatory controls must be reviewed by qualified counsel and responsible professionals before launch. Application code cannot substitute for pharmacy licences, pharmacist registration, medical-device obligations, GST/tax advice, DPDP privacy review, telemedicine review, consumer policy approval, or partner contracts.

MediMart uses MySQL and excludes Redis. Use Windows Task Scheduler or a MySQL-backed job mechanism for scheduled work, and run migrations, checks, tests, private-media migration, payment webhook verification, and backup validation as part of every release.

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

Internal application work can proceed without these credentials. External integrations and production-monitoring features are not production-complete until their providers and policies are supplied.
