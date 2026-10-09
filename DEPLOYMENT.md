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
- SMS provider URL and credentials if transactional SMS is enabled
- A production geocoding endpoint and contactable `GEOCODING_USER_AGENT`
- Cloud object storage settings for uploaded prescriptions, documents, and images
- An authorized licence-registry API URL and credentials, when your regulator or verification provider grants access

When `USE_CLOUD_MEDIA=True`, MediMart uses the S3-compatible storage backend from
`django-storages`. Configure `MEDIA_CLOUD_BUCKET`, the AWS credentials, and the
region. Set `AWS_S3_ENDPOINT_URL` only when using a compatible provider rather
than AWS S3. Uploaded files remain private and are served through expiring signed
URLs; keep bucket-level public access disabled.

MediMart does not scrape government portals. Configure `LICENSE_VERIFICATION_API_URL`
and `LICENSE_VERIFICATION_API_KEY` only for a documented CDSCO, ONDLS, state-regulator,
or authorized verification-provider API. Without these values, applicants can still
submit licence details and evidence, and compliance officers complete the review using
the official portal links shown in the operations center. Keep the resulting registry
payload and reviewer decision as auditable evidence, subject to your retention policy.

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
