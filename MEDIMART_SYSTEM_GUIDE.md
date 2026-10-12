# MediMart System Guide

This document explains how the MediMart website works today: its applications, users, roles, permissions, customer journeys, seller onboarding, catalogue review, prescriptions, payments, delivery, healthcare services, notifications, and operational dashboards.

It is an implementation guide for the current Django project. The source code and database remain the final authority if this document and the running application ever differ.

## 1. Product Scope

MediMart is a healthcare marketplace and care-services platform. It supports:

- Healthcare product discovery and AI-assisted catalogue search.
- Medicines, medical equipment, surgical equipment, diagnostic equipment, lab equipment, personal care, supplements, baby care, fitness, orthopedic, and first-aid products.
- Approved sellers, manufacturers, pharmacies, and healthcare businesses.
- Prescription upload, scanning metadata, manual clinical review, resubmission, and fulfilment limits.
- Cart, saved items, coupons, Razorpay online payments, invoices, delivery assignment, order tracking, returns, refunds, and support.
- Lab tests, home bookings, verified doctors, consultations, health records, dependents, medication reminders, and care plans.
- Health education articles, notifications, audit events, and a guarded MediMart AI assistant.

## 2. Application Architecture

MediMart is a server-rendered Django application with progressive AJAX interactions. The main project packages are:

| App | Responsibility |
| --- | --- |
| `accounts` | Users, roles, profiles, addresses, login, MFA, password reset, location preferences |
| `products` | Product catalogue, categories, brands, images, specifications, clinical profiles, search, equipment views |
| `vendors` | Seller registration, business licences, seller offers, inventory-facing seller tools |
| `cart` | Cart, cart items, saved-for-later/wishlist items, coupon application, quantity updates |
| `prescriptions` | Prescription upload, private files, scan metadata, review, medicine mapping, resubmission |
| `orders` | Checkout, order totals, payments, invoices, order status history, inventory, shipments, returns, refunds |
| `dashboards` | Role-scoped Operations Center, management CRUD, delivery dashboard, seller/license/offer review |
| `healthcare` | Dependents, health records, labs, bookings, consultations, reminders, care plans |
| `extras` | Notifications, email delivery records, support tickets, blog, doctors, content issues |
| `assistant` | Chat endpoint, guarded AI answers, AI catalogue search planning, model failover |
| `reviews` | Product and order reviews |
| `core` | Homepage, geolocation, private media delivery, audit/security helpers, public API/health checks |

### Infrastructure and configuration

- Database: MySQL, normally on `127.0.0.1:3306`.
- Configuration: `.env`, loaded by `MediMart/settings.py`.
- Cache: Django local-memory cache. Redis is not required by the current project.
- Static files: `static/` during development and `staticfiles/` for collected production assets.
- Public media: `media/`.
- Sensitive media: `private_media/`, served through permission-checked views rather than public URLs.
- Payments: Razorpay Standard Checkout and server-side signature/webhook handling.
- Email: Django email backend. Development commonly uses the console backend; production email credentials belong in `.env`.
- External location service: reverse geocoding configured by `GEOCODING_REVERSE_URL`.
- AI: custom OpenAI-compatible or Gemini-compatible endpoint configured by `CHATBOT_API_URL`, with model rotation through `CHATBOT_MODELS`.

## 3. Account Types

Every signed-in account has a Django user and a `UserProfile`. The profile role controls access to MediMart custom panels.

| Role | Main responsibility | Main workspace |
| --- | --- | --- |
| Customer | Shop, upload prescriptions, book healthcare services, track orders | Customer dashboard |
| Vendor | Sell approved healthcare products and manage offers/stock | Vendor dashboard |
| Manufacturer | Submit and manage manufactured equipment/products and required evidence | Vendor dashboard + equipment workflows |
| Pharmacy | Sell medicines subject to seller and licence review | Vendor dashboard |
| Pharmacist | Review prescriptions, validate regulated medicines, and record dispensing decisions | Operations Center |
| Phlebotomist | Handle lab collection assignments, OTP, identity checks, and sample handoff | Operations Center |
| Doctor | Maintain a doctor profile and participate in verified consultations | Doctor dashboard |
| Delivery staff | Handle assigned deliveries and allowed status transitions | Delivery dashboard |
| Support staff | Handle support tickets and customer service records | Support/Operations Center |
| Compliance officer | Review sellers, business licences, regulated evidence, and compliance decisions | Operations Center |
| Catalog manager | Manage catalogue, seller offers, product publication, categories, and brands | Operations Center |
| Operations manager | Coordinate users, sellers, fulfilment, clinical, support, finance, and audits | Operations Center |
| Warehouse manager | Manage warehouses, batches, inventory, shipments, and fulfilment | Operations Center |
| Admin | Full application operations access; normally a trusted staff account | Operations Center and Django Admin |

Role is not the same as a Django superuser. A superuser bypasses the custom capability checks, while ordinary staff should be assigned the appropriate MediMart role and only the capabilities needed for their job.

## 4. Authentication and Account Lifecycle

### Customer registration

1. A visitor opens `/register/`.
2. The customer registration form creates a normal customer account.
3. The user is signed in and redirected to the customer dashboard.
4. The user can add a phone number, profile information, addresses, location, and security settings.

### Professional registration

1. A seller, manufacturer, pharmacy, doctor, delivery worker, or operations user opens `/register/professional/`.
2. The form creates the selected professional role.
3. The account can sign in, but regulated tools remain subject to the relevant onboarding and approval checks.
4. A seller completes `/vendors/register/` and uploads business information and licence evidence before selling.

### Login security

- Login is rate-limited by username and request window.
- Password validation uses Django’s configured validators.
- Password reset and password change use Django’s secure built-in flows.
- Optional TOTP two-factor authentication is configured under `/profile/security/two-factor/`.
- When MFA is enabled, login creates a short-lived pending session and requires a valid TOTP code at `/login/verify/`.
- Audit events record successful login, MFA enable/disable, and MFA completion.
- Sessions, CSRF, secure cookies, clickjacking protection, referrer policy, and security headers are configured in settings and middleware.

### Profile and address

The account profile is reused wherever possible. Checkout uses the user’s saved address; the selected address is also copied into the order as an immutable address snapshot so later address edits cannot change historical orders.

Addresses support name, phone, house/road/locality details, district, city, state, pincode, landmark, country, coordinates, geocoding identifiers, raw location payload, source, and address type. One address is maintained as the default address for a user.

The location controls can:

1. Ask the browser for permission.
2. Send latitude, longitude, and accuracy to `/location/detect/`.
3. Reverse-geocode the coordinates.
4. Save the result in the session and, for an authenticated user, in the profile’s preferred location fields.
5. Fall back to a manual city/state/pincode location through `/location/manual/`.

## 5. Permission Model

The custom authorization layer is in `accounts/permissions.py`. Views use `role_required()` and capability checks rather than relying only on hidden buttons.

### Capabilities

| Capability | Roles |
| --- | --- |
| `dashboard.operations` | Admin, operations manager, compliance officer, catalog manager, warehouse manager, support staff |
| `dashboard.delivery` | Admin, delivery staff |
| `users.manage` | Admin, operations manager |
| `catalog.manage` | Admin, operations manager, catalog manager |
| `seller.manage` | Admin, operations manager, compliance officer |
| `compliance.review` | Admin, operations manager, compliance officer |
| `fulfillment.manage` | Admin, operations manager, warehouse manager |
| `clinical.manage` | Admin, operations manager |
| `support.manage` | Admin, operations manager, support staff |
| `finance.manage` | Admin, operations manager |
| `audit.view` | Admin, operations manager |

### What the checks mean

- Anonymous users can browse public products, public health guides, doctors, and labs.
- A customer can access only their own orders, prescriptions, addresses, healthcare records, consultations, support tickets, and saved items.
- A seller can access only their own vendor profile, licences, offers, and vendor order data.
- A delivery worker can update only assigned orders and only through the permitted delivery transitions.
- Operations pages verify both authentication and the capability for the requested section.
- Superusers are allowed through the custom capability gate, but sensitive operations should still be audited and separated operationally.
- The default Django Admin remains available at `/admin/` for authorized Django staff/superusers. It is not removed; it complements the custom role-based panels.

## 6. Customer Journey

### Discover

The homepage loads active categories, featured products, equipment, published guides, verified doctors, active lab tests, marketplace statistics, and the customer’s latest prescription state when signed in.

The catalogue supports:

- `/products/` for the product listing.
- Category and product-type routes for medicines and equipment.
- Product detail pages with images, specifications, seller offers, safety classification, prescription/licence flags, and clinical information when available.
- Product comparison.
- Recently viewed products stored in the session.
- Save for later/wishlist operations.
- Stock alerts and price alerts.
- AI search at `/search/ai/` and search suggestions at `/search/suggestions/`.

AI search is a search planner, not a prescriber. It converts a natural-language request into safe product/lab terms, then the database remains authoritative for actual results. If the configured AI service is unavailable, MediMart uses its local healthcare term expansion and catalogue fallback.

### Product safety gates

Each product can carry:

- Product type and category.
- SKU, barcode, manufacturer, composition, pack size, unit, weight, and dimensions.
- MRP and selling price.
- Prescription requirement.
- Business licence requirement and required licence type.
- Regulatory classification and notes.
- Safety classification: OTC, prescription, controlled, Schedule X, or prohibited.
- Recall state: clear, quarantined, or recalled.
- Quantity limit, minimum shelf life, and cold-chain requirement.

Prescription/controlled products require an approved current prescription that authorizes the product and quantity. Schedule X and prohibited items are automatically prevented from being active by the product model rules.

### Cart and checkout

1. The customer selects an approved active seller offer.
2. The offer is added to the customer’s cart.
3. Cart quantity is validated against product limits, seller stock, active status, recall/quarantine rules, and prescription requirements.
4. The customer selects the default or another saved delivery address.
5. The customer applies a valid coupon; the server recalculates the discount and never trusts a browser total.
6. The order reserves inventory inside a transaction for the configured reservation period.
7. The order stores subtotal, discount, delivery charge, total, payment method, and address snapshot.
8. Razorpay is the preferred online payment method. The server creates the Razorpay order, the browser opens Standard Checkout, and the server verifies the returned signature.
9. A successful payment changes payment/order state only after server-side verification or a validated Razorpay webhook.
10. Failed/cancelled payments do not mark the order paid. Reserved stock can be released through the order lifecycle.

Payment records include gateway order/payment IDs, signature, status, captured/refunded amounts, gateway metadata, failure details, verification timestamps, and payment events. Payment webhook events are idempotently recorded with an event ID and payload hash.

### Order lifecycle

Customer-visible order states are:

`Pending -> Confirmed -> Processing -> Packed -> Shipped -> Out for Delivery -> Delivered`

Cancellation, return, and refund outcomes can move an order to `Cancelled`, `Returned`, or `Refunded`. Every meaningful transition creates an `OrderStatusHistory` row with status, note, actor, and timestamp. The order detail page can render this as a tracking timeline.

The customer can view orders, reorder eligible previous items, download an invoice PDF, cancel where allowed, start a return request, and follow notifications.

## 7. Product and Seller Onboarding

There are two product submission paths:

1. Add an offer for a product that already exists in the MediMart catalogue.
2. Submit a new catalogue product and an initial seller offer together.

### Example: adding a new equipment product

1. A manufacturer signs in using the manufacturer role.
2. The manufacturer registers the business at `/vendors/register/` and supplies business type, owner/contact data, GST information, licence number, address, and private documents.
3. The registration creates a business licence record in `PENDING` state. Required licence types include medical-device sale, manufacturing, and import categories.
4. The manufacturer opens `/vendor-products/catalog/add/` and supplies the product name, type, price, stock, manufacturer, descriptions, media, regulatory classification, licence requirement, and equipment details.
5. MediMart stores the new product as inactive and creates the seller offer as unapproved. It is not publicly purchasable yet.
6. A compliance officer or authorized operations/admin reviewer checks the seller, licence document, expiry date, business identity, licence type, and product/regulation compatibility.
7. A catalog manager, operations manager, or admin checks product naming, category, images, specifications, pricing, required fields, safety flags, recall state, and publication quality.
8. If the licence is valid and the offer passes review, the reviewer approves the offer. The offer becomes active and approved, and the product becomes active/published.
9. The manufacturer can then update price, stock, delivery time, warranty, offer text, and active state from the vendor panel. An edit sends the offer back for approval.

### Who verifies what?

| Item | Submitted by | Verified/approved by | Publication gate |
| --- | --- | --- | --- |
| Seller business | Vendor, pharmacy, manufacturer, equipment seller | Compliance officer, operations manager, or admin | Seller must be approved and active |
| Business licence | Seller | Compliance officer, operations manager, or admin | Document required, not expired, status verified |
| Existing product offer | Seller | Catalog manager, operations manager, or admin | Offer approved and active |
| New catalogue product | Seller/manufacturer | Catalog manager/operations/admin, with compliance checks where regulated | Product active plus approved offer |
| Prescription | Customer | Clinical reviewer through `clinical.manage` | Approved, current, and mapped to product/quantity |
| Doctor profile | Doctor | Authorized clinical/admin reviewer | Profile is marked verified before public listing |
| Delivery state | Delivery staff for assigned orders; operations for assignment | Delivery/operations rules | Only allowed status transitions |

The current implementation records government verification sources such as applicant supplied, ONDLS manual verification, or CDSCO medical-device portal, but it does not automatically query a government licence API. A reviewer must document the verification decision and notes.

### Existing product offer flow

When a seller uses `/vendor-products/add/`, the seller selects an existing product and submits price, stock, delivery time, warranty, and offer text. The offer starts unapproved. Updating an existing offer also resets approval so a reviewer can reassess changes. Offers with order history are archived instead of hard-deleted.

## 8. Operations Center and Panels

The custom Operations Center is available at `/admin-dashboard/` to users with `dashboard.operations`. It is separate from, and used alongside, the default Django Admin at `/admin/`.

### Management sections

The Operations Center currently exposes capability-controlled sections for:

- Users.
- Products, categories, brands, and seller offers.
- Sellers and business licences.
- Orders, warehouses, inventory batches, shipments, and returns.
- Prescriptions, doctors, lab tests, lab bookings, and consultations.
- Coupons.
- Blog posts and blog categories.
- Notifications and email delivery records.
- Payments and refunds.
- Support tickets.
- Audit trail.

Most management lists support search, pagination, status display, edit/create forms where appropriate, and guarded POST actions. Records are audited when operational decisions change state.

### Review actions

- Seller review: approve only after required compatible current licence verification; suspend disables the seller and its offers.
- Licence review: approve only when a document exists and the licence has a valid expiry date; store reviewer, timestamp, status, and notes.
- Offer review: approve only when the seller has a compatible verified licence for regulated products; publish product and offer together.
- Prescription review: set review status, reviewer, notes, clarification/rejection reason, and product mappings; an approved prescription must map at least one product.
- Delivery assignment: assign an order only to a user with the delivery staff role; assignment is recorded in status history and audit trail.
- Returns/refunds: support and finance users manage request states and refund records without deleting the original order history.

### Delivery dashboard

`/delivery-dashboard/` is available to delivery staff and admin. A delivery worker sees assigned active orders and can move only:

- `Shipped -> Out for Delivery`
- `Out for Delivery -> Delivered`

Operations staff assign or remove delivery ownership from the order management flow. Each change creates status history, an audit event, and a customer notification.

### Seller dashboard

`/vendor-dashboard/` shows seller approval state, licence records, offer counts, active/pending products, low stock, total stock, recognized revenue, units sold, fulfilment items, and recent offers/orders. The seller can manage only records belonging to their vendor profile.

## 9. Prescription System

Prescription files are private and delivered through a protected endpoint. A customer can:

1. Open `/prescriptions/upload/`.
2. Upload a permitted document and provide patient, doctor, clinic, date, medicines, and consent details.
3. Receive a pending-review record and notification.
4. View the detail page and scan status/summary/flags.
5. Resubmit if the reviewer requests information.
6. Cancel while the review is still pending, under review, or awaiting information.

Prescription states include pending, under review, needs information, approved, rejected, expired, and cancelled. Scan status is tracked separately. Reviewers map prescription items to catalogue products, dosage/instructions, requested quantity, and fulfilment quantity.

An approved prescription is usable only when it is current, within its validity date, within its fulfilment limit, and authorizes the selected product and quantity. The system is designed to support clinical review; AI search and the chatbot must not diagnose or replace a clinician.

## 10. Inventory, Warehousing, and Fulfilment

Inventory is represented by seller offers plus warehouse batches. A batch records:

- Warehouse and seller offer.
- Batch number.
- Manufacture and expiry dates.
- Quantity and reserved quantity.
- Quarantine state and reason.
- Recall reference.
- Temperature log for cold-chain operations.

The available quantity is quantity minus reserved quantity. Quarantined, expired, empty, or below minimum shelf-life batches are not sellable. Inventory movements record receipts, reservations, releases, sales, returns, and adjustments with a reference and actor.

Shipments record warehouse, courier, tracking number, promised time, shipment status, and shipment events. Warehouse managers operate inventory and shipment records; delivery staff operate the last-mile status transitions allowed by the delivery dashboard.

## 11. Payments, Invoices, Returns, and Refunds

Razorpay flow:

1. Customer places an order with an address and Razorpay selected.
2. Backend validates the order and amount, then creates a Razorpay order using server-only credentials.
3. Frontend opens Razorpay Standard Checkout in a modal.
4. Razorpay returns payment ID, order ID, and signature.
5. Backend verifies the HMAC signature and matches the payment to the local order and amount.
6. Webhooks provide a second gateway event path. Duplicate events are ignored using event IDs/payload hashes.
7. Only verified/captured payment data can settle the order and allow fulfilment.

Never put `RAZORPAY_KEY_SECRET` or other private credentials in templates, JavaScript, Git, or chat responses. Only the public key ID may be exposed to the browser.

Invoices are available from the order detail flow and can be rendered as a PDF. A payment can have multiple refund records, each with amount, reason, state, gateway refund ID, requester, and timestamps.

## 12. Healthcare Services

Signed-in customers can use `/healthcare/` for a personal health dashboard containing:

- Dependents/family members.
- Health records stored as protected files.
- Medication reminders linked to products and dependents.
- Lab bookings and partner information.
- Doctor consultations and consultation messages.
- Active care-plan membership.

Public users can browse active labs and verified doctors, but booking and record access require authentication. Private health records, lab reports, prescription files, doctor credentials, and support attachments are delivered through protected `core` views.

## 13. Notifications, Support, and Blog

Notifications are in-app records linked to a user and can be marked read. Notification deliveries retain email channel, destination, attempt count, retry timing, and delivery state. The current implementation keeps SMS out of the normal notification flow; email and in-app notifications are the supported channels.

Support users can see all support tickets; ordinary customers can see only their own tickets and messages. Staff replies move open tickets to in progress and create a notification for the customer.

The blog shows only published posts to visitors. Operations/catalog staff manage posts and categories through the Operations Center. Blog content can be reported through content issues for review.

## 14. AI Assistant and AI Search Safety

The assistant endpoint is `/assistant/chat/` and accepts a POST message. It is rate-limited and truncates oversized input. Before an external model is called, it:

- Blocks requests for passwords, OTPs, payment credentials, private files, prescriptions, API keys, and internal database details.
- Answers basic order questions from the signed-in user’s own latest order data.
- Supplies the AI only with public catalogue/lab context, not unrestricted database access.
- Redacts likely emails, phone numbers, and credentials from output.
- Falls back to local catalogue/order responses when the provider is unavailable.

AI model failover uses the configured list in `CHATBOT_MODELS`. Retryable provider failures place a model on a short cache cooldown and the next configured model is tried. This is availability failover, not permission escalation: no model is allowed to bypass MediMart authorization.

## 15. Data Protection and Auditability

Sensitive values and documents have additional protections:

- Bank account data and MFA secrets use encrypted fields/storage patterns.
- Private documents use private storage and permission-checked download views.
- Customer data is filtered by owner in customer-facing views.
- Order addresses are snapshotted for historical integrity.
- Payment events are idempotency-protected.
- Audit events record security, seller, offer, prescription, delivery, management, and payment decisions.
- CSRF, rate limits, password validators, MFA, secure session settings, and security headers reduce common web risks.

Production deployment should set a strong `SECRET_KEY`, `FIELD_ENCRYPTION_KEY`, non-debug mode, allowed hosts, HTTPS, secure cookies, real email credentials, real Razorpay webhook secret, and an approved media storage provider.

## 16. Practical Runbooks

### Runbook A: add and publish a product

1. Create or sign in to a manufacturer/vendor/pharmacy account.
2. Complete seller registration and upload the required business document.
3. Wait for compliance to verify the licence if the business type requires one.
4. Open the vendor product area.
5. Choose an existing catalogue product or submit a new catalogue product.
6. Enter accurate product, regulatory, safety, pricing, stock, and media details.
7. Submit the offer. It remains unapproved and the new product remains inactive.
8. Compliance reviews the seller licence and product regulation compatibility.
9. Catalog/operations reviews quality, category, product fields, images, specifications, recalls, and publication state.
10. Approve the offer. The product and offer become available only after all gates pass.
11. Maintain stock and price from the vendor dashboard. Any material offer edit returns to review.

### Runbook B: approve a seller

1. Open Operations Center -> Sellers.
2. Open the seller record and inspect business type, contact, GST, licence number, and documents.
3. Open Operations Center -> Business Licences.
4. Inspect the private licence file, expiry date, licence type, authority, and external verification notes.
5. Mark the licence verified only when the document is present and current.
6. Return to the seller review action and approve only when a required compatible licence exists.
7. Audit the decision and notify the seller through the configured workflow.

### Runbook C: fulfil a paid order

1. Confirm payment status is verified/paid or the order uses an approved COD path.
2. Confirm reservation and sellable inventory batches.
3. Process and pack the order, respecting prescription and cold-chain rules.
4. Create/update shipment, warehouse, courier, and tracking fields.
5. Assign a delivery worker from the order management flow.
6. The delivery worker moves the order through allowed last-mile states.
7. The customer receives status notifications and sees the order timeline.
8. For eligible issues, create a return request and process the related refund without deleting the original history.

### Runbook D: review a prescription

1. A customer uploads the file and required patient/doctor information.
2. The system stores the private file and creates a pending record.
3. A clinical reviewer opens the prescription record.
4. Review the image/document, scan flags, dates, doctor information, requested medicines, and customer notes.
5. Request clarification, reject with a reason, or map items to products and approve.
6. An approved record can be used only for current authorized products and quantities.
7. Notify the customer and keep the review audit trail.

## 17. Important URLs

| Area | URL |
| --- | --- |
| Home | `/` |
| Customer registration | `/register/` |
| Professional registration | `/register/professional/` |
| Login | `/login/` |
| Customer dashboard | `/dashboard/` |
| Profile/security | `/profile/` and `/profile/security/two-factor/` |
| Addresses | `/addresses/` |
| Products | `/products/` |
| AI search | `/search/ai/` |
| AI assistant | `/assistant/chat/` |
| Cart | `/cart/` |
| Checkout | `/checkout/` |
| Orders | `/orders/` |
| Prescriptions | `/prescriptions/` |
| Vendor registration | `/vendors/register/` |
| Vendor dashboard | `/vendor-dashboard/` |
| Vendor products | `/vendor-products/` |
| Operations Center | `/admin-dashboard/` |
| Delivery dashboard | `/delivery-dashboard/` |
| Doctor dashboard | `/doctor-dashboard/` |
| Healthcare dashboard | `/healthcare/` |
| Labs | `/labs/` |
| Consultations | `/consultations/` |
| Notifications | `/notifications/` |
| Support | `/support/` |
| Blog | `/blog/` |
| Django Admin | `/admin/` |

## 18. Local Operations

The project expects MySQL rather than SQLite. Local database administration can be started with:

```text
mysql -u root -p
```

Enter the local MySQL password interactively. Do not place the password in this document or source control.

Typical project commands are:

```text
python manage.py check
python manage.py migrate
python manage.py createsuperuser
python manage.py test
python manage.py collectstatic
```

The default Django Admin user is separate from ordinary MediMart roles. Create a trusted superuser only for Django Admin access, and create role-based MediMart accounts for day-to-day operations.

## 19. Current Boundaries and Operational Notes

- Licence verification is a manual review workflow; there is no live government licence lookup API in the current implementation.
- AI is a guarded search/support layer and must not diagnose, prescribe, or reveal private information.
- Provider failover requires multiple models to be configured in `CHATBOT_MODELS`; otherwise the local fallback is used.
- Email delivery depends on production SMTP configuration; the console backend is suitable for development only.
- Razorpay real-payment readiness depends on correct production keys, webhook configuration, HTTPS, reconciliation, refund policy, and merchant account configuration.
- Media production readiness depends on private storage, backups, virus scanning, size limits, and a cloud/object-storage strategy.
- Role assignment should be controlled by trusted administrators; never let an ordinary customer self-promote to an operations or compliance role.

## 20. Source-of-Truth Files

The most important implementation locations are:

- `MediMart/settings.py` for database, security, email, payment, AI, media, and environment configuration.
- `MediMart/urls.py` for application routing.
- `accounts/models.py` and `accounts/permissions.py` for profiles, addresses, roles, and capability checks.
- `vendors/models.py` and `vendors/views.py` for seller/licence/offer workflows.
- `products/models.py` and `products/views.py` for catalogue and product safety rules.
- `dashboards/views.py` for Operations Center sections, CRUD, review actions, and delivery assignment.
- `orders/models.py` and `orders/views.py` for checkout, payment, inventory, fulfilment, invoices, returns, and refunds.
- `prescriptions/models.py` and `prescriptions/views.py` for clinical review.
- `healthcare/` for care services.
- `extras/` for notifications, support, blog, and doctors.
- `assistant/services.py` for AI provider selection, model failover, redaction, and local fallback.

## Additive 102-Item System Coverage Update

This section was appended without deleting any system-guide content. The complete requested surface is tracked in `ONE_MG_GAP_ANALYSIS.md` across safety, medicine knowledge, diagnostics, consultations, family care, search and AI, payments, delivery, operations, reliability, and UI/UX.

Current working workflows include pharmacist-only prescription review with validation and clarification, Schedule H/H1/NDPS/habit-forming classification foundations, batch and dispensing traceability, temperature excursion quarantine, product variants and pharmacist-reviewed alternatives, moderated questions and review trust controls, lab capacity-safe cancellation/rescheduling, delivery assignment with hashed OTP and private proof, MySQL migrations, and per-user action capability overrides.

Operational boundaries remain explicit: AI must not diagnose or prescribe; licence verification remains manual; live courier, lab, consultation, storage, email, payment, and monitoring providers require configured accounts; legal and clinical approval remains mandatory; and the roadmap must not be marked complete merely because a database model exists.

### Additive single-model AI policy

The current Groq configuration intentionally uses only `openai/gpt-oss-120b` for AI chat and AI catalogue search. `CHATBOT_MODELS` contains one model, so no additional model requests are made when a call fails; the application uses its guarded local fallback instead.

### Additive Groq provider configuration

The assistant and AI catalogue search share MediMart's OpenAI-compatible provider adapter. Groq is configured through `CHATBOT_API_URL=https://api.groq.com/openai/v1`, `CHATBOT_PROVIDER=openai_compatible`, a server-side `CHATBOT_API_KEY`, and `CHATBOT_MODELS` for model failover. Groq credentials must remain in `.env` or the deployment secret manager and must never be placed in templates, JavaScript, Markdown, logs, or API responses.

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

## Additive Authoritative Project Reference (2026-10-13)

This section is the current implementation reference for the complete project. It is intentionally additive: earlier sections are preserved for historical context, while this section explains the present code paths, ownership rules, data flow, commands, and known boundaries in one place. When an earlier statement conflicts with this section, the running source code and this dated section should be checked together.

### A. Technology and runtime

MediMart is a server-rendered Django application with HTML templates, Bootstrap-compatible CSS, vanilla JavaScript, MySQL persistence, and selected JSON/AJAX endpoints. It is not a single-page React application.

The normal local runtime is:

- Windows/XAMPP development host.
- Python virtual environment at `.venv/`.
- Django 6.1.1.
- MySQL through `mysqlclient`.
- Pillow for image validation and processing.
- ReportLab for invoice PDFs.
- Razorpay SDK for payment-provider requests.
- `cryptography` for encrypted database fields and protected secrets.
- `PyOTP` and `qrcode` for TOTP two-factor authentication and Google Authenticator QR enrollment.
- `django-storages[s3]` for optional private/public S3-compatible object storage.
- `python-dotenv` for `.env` configuration.

The application starts from `manage.py`, loads `MediMart/settings.py`, then routes requests through `MediMart/urls.py`. Each domain app owns its models, forms, views, URLs, templates, migrations, and optional admin configuration.

The authoritative configuration layers are:

1. Process environment variables.
2. The local `.env` file loaded by Django.
3. Safe development defaults in `MediMart/settings.py`.

Production must override development defaults. In particular, use `DEBUG=False`, a dedicated MySQL user, a strong secret key, an encryption key, HTTPS, secure cookies, private media storage, real SMTP, and a signed Razorpay webhook secret.

### B. Request and data-flow model

Most page requests follow this sequence:

1. The browser requests a URL.
2. Django middleware applies security headers, sessions, CSRF protection, authentication, active-account checks, and messages.
3. The URL resolver selects an app view.
4. The view checks authentication, role/capability, ownership, and request method.
5. A form validates user input and uploaded files.
6. The view reads or writes model records, normally inside `transaction.atomic()` when money, inventory, or capacity is involved.
7. Domain events are written to audit/history tables and customer notifications are created.
8. The view redirects or renders a template.

Customer-owned records are filtered by `request.user`. Staff records are filtered by capability and, for delivery staff, assignment. Private files are not public URLs; they are downloaded through `core/private_media.py`, which checks ownership or an authorized operational role.

Money and inventory operations must be treated as server-authoritative. Browser totals, browser payment callbacks, hidden buttons, and manually changed URLs are not trusted sources of truth.

### C. App ownership and important records

| App | Main records and responsibility |
| --- | --- |
| `accounts` | Django users, `UserProfile`, roles, addresses, capability overrides, login identifiers, MFA settings |
| `products` | Product, Category, Brand, ProductImage, ProductSpecification, ProductVariant, ProductClinicalProfile, ClinicalInteraction, ProductSubstitute, ProductQuestion, SearchQuery, alerts |
| `vendors` | Vendor, BusinessLicense, VendorProduct and seller-facing catalogue operations |
| `cart` | Cart, CartItem, Wishlist, WishlistItem and coupon selection state |
| `prescriptions` | Prescription, PrescriptionItem, PrescriptionReview and scan/validation state |
| `orders` | Order, OrderItem, OrderStatusHistory, Payment, PaymentEvent, charge breakdown, inventory, shipment, return, refund, recall, settlement, chargeback, credit note |
| `healthcare` | Dependents, HealthRecord, LabPartner, LabTest, LabCollectionSlot, LabBooking, LabSampleEvent, LabReportValue, Consultation, ConsultationMessage, ConsultationPayment, reminders, care plans |
| `extras` | DoctorProfile, PharmacistProfile, Notification, NotificationDelivery, SupportTicket, SupportMessage, BlogPost, ContentIssue, QualityComplaint |
| `reviews` | Customer reviews, seller replies, helpfulness votes, abuse reports and moderation state |
| `dashboards` | Capability-controlled Operations Center, management CRUD forms, review actions, assignment, delivery dashboard |
| `assistant` | Guarded chat request handling, local account-aware answers, public catalogue context, AI provider adapter, response caching |
| `core` | Home page, location, audit events, private file delivery, health checks, public catalogue API, shared security helpers |

### D. Role and capability authority

The role is stored in `accounts.UserProfile.role`. The capability mapping in `accounts/permissions.py` is the authorization authority for custom MediMart pages. The current capability ownership is:

| Capability | Current roles |
| --- | --- |
| `dashboard.operations` | Admin, Operations Manager, Compliance Officer, Catalog Manager, Warehouse Manager, Support Staff, Pharmacist, Phlebotomist |
| `dashboard.delivery` | Admin, Operations Manager, Warehouse Manager, Delivery Staff |
| `users.manage` | Admin, Operations Manager |
| `catalog.manage` | Admin, Operations Manager, Catalog Manager |
| `seller.manage` | Admin, Operations Manager, Compliance Officer |
| `compliance.review` | Admin, Operations Manager, Compliance Officer |
| `fulfillment.manage` | Admin, Operations Manager, Warehouse Manager |
| `clinical.manage` | Admin, Operations Manager, Pharmacist, Phlebotomist |
| `clinical.prescription_review` | Admin, Operations Manager, Pharmacist; pharmacist accounts must be verified |
| `clinical.lab_operations` | Admin, Operations Manager, Phlebotomist |
| `clinical.doctor_operations` | Admin, Operations Manager |
| `support.manage` | Admin, Operations Manager, Support Staff |
| `finance.manage` | Admin, Operations Manager |
| `audit.view` | Admin, Operations Manager |

There are two separate checks:

- `role_required()` protects a view at the URL boundary.
- `has_capability()` protects a business action or management section.

Capability overrides can grant or deny one capability for one user. They are useful for temporary delegation and must have a reason and granting account. They do not replace least privilege or a proper primary role.

The Django Admin is a separate staff/superuser surface. A user being a MediMart Admin role does not automatically mean the user is a Django superuser. A superuser bypasses custom capability checks and therefore must be tightly controlled.

### E. Complete account lifecycle

#### Customer account

1. Visitor opens `/register/`.
2. `CustomerRegistrationForm` creates a Django user and a `customer` profile.
3. Password validators and email uniqueness checks run before creation.
4. The account is signed in and redirected to the customer dashboard.
5. The customer adds phone, profile, address, location, prescriptions, and health records as needed.

#### Professional account

1. Applicant opens `/register/professional/`.
2. The form permits vendor, manufacturer, pharmacy, or doctor as the initial business role.
3. The account is created, but professional capabilities do not prove legal or clinical approval.
4. Vendors, pharmacies, and manufacturers complete seller registration with business and licence evidence.
5. Doctors complete a doctor profile and submit registration and qualification evidence.
6. Compliance or clinical reviewers verify the evidence before public publication or regulated operation.

Delivery, support, compliance, catalogue, operations, warehouse, pharmacist, and phlebotomist accounts should be created by an authorized operations administrator rather than exposed as public self-registration choices.

#### Sign-in and MFA

The login identifier may be a username, email address, or normalized Indian phone number. Login is rate-limited and uses Django password authentication. When MFA is enabled, the password login creates a five-minute pending session; only a valid TOTP code completes authentication.

MFA setup creates an `otpauth://totp/MediMart/...` URI and renders a QR code inline. The QR and secret are not saved as public files. The encrypted MFA secret is stored only after the user proves control of the authenticator code. Google Authenticator, Microsoft Authenticator, and other standards-compatible TOTP apps can scan it.

### F. Catalogue and product workflow

The catalogue has two layers:

- A `Product` is the master catalogue item and contains clinical, regulatory, descriptive, pricing, image, and safety fields.
- A `VendorProduct` is one seller's offer for that product and contains seller price, stock, delivery promise, warranty, rating, active state, and approval state.

A product can have many sellers. A product should not become purchasable merely because a master record exists: it needs an active product and at least one approved active seller offer.

#### Add an existing product offer

1. Vendor signs in and opens `/vendor-products/add/`.
2. Vendor selects an existing product and enters price, stock, delivery time, warranty, and offer text.
3. The server checks duplicate offers for the same vendor/product.
4. The offer is saved with `is_approved=False`.
5. Catalogue/compliance/operations staff review the seller, licence, price, stock, and regulated-product compatibility.
6. Approval activates the offer. A later material edit resets approval.

#### Add a new catalogue product

1. Manufacturer/vendor opens `/vendor-products/catalog/add/`.
2. The form validates product fields, image, price, product type, regulation, licence requirements, and stock.
3. The product is created inactive and an initial offer is created unapproved.
4. Compliance verifies licences and regulated evidence.
5. Catalogue staff validate naming, category, images, specifications, price, clinical fields, returnability, storage, and warnings.
6. An authorized reviewer approves the offer and publishes the product only after all gates pass.

Product safety data can include composition, strength, dosage form, route, therapeutic class, interactions, manufacturer, country of origin, licence/GST/HSN fields, variants, substitutes, storage, warranty, cold-chain state, recall state, shelf-life requirements, prescription requirement, schedule classification, and quantity limits.

### G. Prescription and pharmacist workflow

1. Customer uploads a PDF/image through `/prescriptions/upload/`.
2. File type, size, and private-document validation run before storage.
3. The record is created in a pending state and the file is stored privately.
4. Scan metadata records safety status, summary, confidence/flags, and completion time. OCR/AI data does not approve a prescription.
5. A verified pharmacist opens the prescription review queue.
6. The reviewer checks patient name, doctor name, registration number, prescription date, validity, dosage, duration, quantity, alterations, and requested products.
7. The reviewer maps only approved catalogue products and records item-level dosage, instructions, quantity, decision, notes, reviewer, and timestamp.
8. The reviewer chooses approved, partially approved, rejected, needs information, or under review.
9. Approval is blocked when required validation flags remain or no authorized item exists.
10. The customer receives an in-app notification and can resubmit when clarification is requested.
11. Checkout checks that the prescription is current, approved/partially approved, authorizes the specific product, and has enough remaining quantity/fulfilment allowance.
12. Dispensing records link the pharmacist, licence, batch, quantity, substitution decision, and approval decision when the dispensing workflow is used.

The prescription file must be available to the verified clinical reviewer through the protected media permission. No prescription or medical file should be exposed through a public media URL.

### H. Cart, checkout, payment, and invoice workflow

1. Customer adds an active approved seller offer to cart.
2. Cart validates seller, product, stock, recall/quarantine state, quantity limits, and prescription authorization.
3. Checkout validates the saved address and recalculates all totals on the server.
4. Coupon validation checks active dates, minimum order, usage limit, and one-use-per-customer rules.
5. Inventory batches are locked and reserved in a transaction.
6. The order stores an address snapshot, order lines, seller snapshot fields, payment method, status, and reservation expiry.
7. A `Payment` row and `OrderChargeBreakdown` row are created.
8. Razorpay checkout creates or reuses a provider order; the browser only receives the public key and safe order data.
9. Server-side signature verification and amount/currency/order matching are required.
10. Razorpay webhooks are verified with the webhook secret and recorded as idempotent `PaymentEvent` rows.
11. Only a validated captured payment changes the local payment/order state to paid/confirmed.
12. Invoice HTML and PDF read seller details from each order line's vendor and read charges from the charge breakdown.

The payment source of truth is the verified provider event plus the local reconciliation record, not the browser callback alone. A failed payment must not make an order paid. Reservation expiry is handled by the release command or an equivalent scheduler.

### I. Order, warehouse, shipment, and delivery workflow

The intended operational path is:

`Pending -> Confirmed -> Processing -> Packed -> Shipped -> Out for Delivery -> Delivered`

The customer can cancel only in the allowed early states. Returns start only after delivery and inside the configured return window.

#### Warehouse and batch steps

1. Warehouse manager creates a warehouse.
2. Staff create an inventory batch for a seller offer.
3. Batch data includes batch number, MRP, supplier, invoice, manufacture date, expiry, quantity, dispensing pharmacy, storage range, quarantine state, and recall reference.
4. Reservation creates an inventory movement and increments reserved quantity.
5. Cancellation or reservation expiry releases the reservation.
6. Delivery completion converts reservations into sale movements.
7. Accepted returns can restock a traced batch exactly once.
8. Temperature readings outside the configured range automatically mark a batch as quarantined for investigation.

#### Last-mile steps

1. Operations or warehouse staff assign only a `delivery_staff` account to the order.
2. Delivery staff see only assigned active orders.
3. A shipped order can move to out-for-delivery.
4. The system issues a delivery OTP and notifies the customer.
5. The customer shares the OTP at delivery.
6. Delivery staff verify the OTP, optionally attach proof, record recipient name, create a shipment event, and complete delivery.
7. Order history, audit event, and customer notification are created.

Courier API tracking, NDR/RTO automation, cash collection reconciliation, and reverse pickup require an external courier or an approved manual operational process.

### J. Returns, refunds, recalls, and complaints

#### Customer return path

1. Customer opens a delivered order and selects an order item.
2. The server checks ownership, delivery date, seven-day window, and remaining returnable quantity.
3. Customer submits reason, quantity, description, and evidence if required.
4. Support/operations reviews and can approve, reject, schedule pickup, mark received, inspect, quarantine, accept, or restock.
5. Finance creates a refund queue record only after receipt and an accepted/restocked inspection decision.
6. Razorpay or the configured payment provider processes the refund.
7. The webhook or refund worker completes the refund, updates payment/refund/return state, writes order history, and notifies the customer.

#### Recall path

1. Compliance creates a recall notice for a product and optionally a batch.
2. Activation quarantines the affected batch or product and prevents normal sale.
3. Affected order lines and customers are identified.
4. Customers receive a recall notification with the order link.
5. Support/operations coordinates reverse pickup and refund/replacement according to the approved policy.
6. Completion is recorded with the recall reference and audit trail.

Quality complaints, adverse events, temperature excursions, and evidence files should be kept as operational records with ownership, status, reviewer, resolution, and audit metadata.

### K. Lab workflow

1. Operations creates a lab partner and records accreditation, licence, branch, operating hours, service area, contact, and quality evidence.
2. Staff create active lab tests/packages with image, sample type, preparation, price/MRP, home-collection flag, and report SLA.
3. Staff create collection slots with start/end, capacity, blackout state, and active state.
4. Customer selects a test, dependent, address, and available collection slot.
5. A transaction locks the slot, checks capacity, increments `booked_count`, creates a lab invoice, and creates a requested sample event with accession/barcode data.
6. Staff confirm, collect, process, request recollection, or mark the report ready using allowed status transitions.
7. Phlebotomist assignment, identity verification, collection OTP, proof of collection, accession barcode, and chain-of-custody events are recorded.
8. Structured report values should include value, unit, reference range, abnormal flag, age/sex applicability, explanation status, and corrected-version history.
9. Customer can view only their own booking/report through protected access.
10. Cancellation/rescheduling releases or moves slot capacity and records a sample event.

Lab partner APIs, digital result ingestion, invoice payment, settlements, no-show fees, and disputes are not automatically connected without a partner integration or documented manual workflow.

### L. Doctor consultation workflow

1. Doctor creates/updates a profile, specialty, qualification, registration, fee, clinic, mode, availability, and credential evidence.
2. A clinical/operations reviewer verifies the doctor before public listing.
3. Customer selects a verified doctor and submits symptoms, history, dependent, mode, and optional scheduled time.
4. Server checks published availability and capacity, creates a consultation, and creates a pending consultation payment ledger row.
5. Operations confirms, starts, completes, or cancels the consultation through allowed transitions.
6. Customer and assigned doctor can open the private consultation and exchange messages/attachments.
7. Doctor notes, advice, referral, follow-up end time, and signed e-prescription are private clinical records.
8. Follow-up access is valid only until the stored follow-up deadline.

The current project stores consultation payment records and private messaging data, but a complete provider-backed video/chat payment and refund integration still requires an external provider and additional operational policy.

### M. Notifications and support

Notifications are created by domain workflows for order placement/status, prescription review, returns, refunds, seller review, lab booking changes, consultation changes, delivery OTP, and support replies.

- In-app notifications remain in the user notification center until read or retained according to policy.
- Toasts are short-lived and are not the permanent record.
- Email delivery attempts are stored separately with retry state and error information.
- Notification queue processing is run by `process_notification_queue`.
- Support staff can view all support tickets; customers can view only their own tickets.
- Staff replies move an open ticket to in-progress and notify the customer.

### N. AI chat and AI catalogue search

There are two related but separate AI paths:

#### Chatbot

`POST /assistant/chat/` accepts a short message, rate-limits the request, blocks sensitive requests, checks local account-scoped order/lab/consultation answers first, and only then may call the configured provider with public catalogue context.

Private account status is answered locally from the authenticated user's records. Anonymous users never receive another user's account information. Passwords, OTPs, payment credentials, private documents, prescriptions, medical records, API keys, and internal database details are blocked or redacted.

#### AI search

The AI search planner receives the shopping request and a bounded list of public product/lab labels. It returns search terms, lab terms, intent, and a short summary. The database performs the actual filtering and remains authoritative. When AI is unavailable, local healthcare aliases and normal catalogue search are used.

The current local configuration uses one Groq OpenAI-compatible model. Caching and deduplication reduce duplicate provider calls. Provider credentials remain server-side in `.env`; never copy an API key into Markdown, templates, JavaScript, or logs.

### O. CRUD ownership matrix

| Data | Create | Review/update | Delete/deactivate |
| --- | --- | --- | --- |
| Customer profile/address | Customer | Customer; operations for support | Customer; referenced addresses remain protected |
| Seller/vendor | Vendor applicant | Compliance/operations | Deactivate/suspend; historical orders protect references |
| Business licence | Vendor/applicant | Compliance/operations | Retain evidence; do not erase regulated history casually |
| Product master | Catalog/operations or seller submission | Catalog, compliance, operations | Deactivate/recall; preserve historical order references |
| Seller offer | Vendor | Catalog/operations | Archive when order history exists |
| Inventory batch | Warehouse staff | Warehouse/compliance | Quarantine or adjust with movement history |
| Prescription | Customer | Verified pharmacist/clinical reviewer | Customer cancellation; retain review history |
| Order | Customer checkout | Operations/warehouse/delivery by transition | Never hard-delete normal order history |
| Payment/refund | Checkout/provider/finance | Finance/provider webhook | Preserve events and reconciliation evidence |
| Return | Customer | Support/operations/finance | Cancel only through allowed customer state |
| Lab booking/report | Customer/provider/staff workflow | Phlebotomy/lab operations | Cancel or correct with chain-of-custody history |
| Consultation | Customer/operations workflow | Doctor/clinical operations | Cancel/close; retain private clinical history |
| Support ticket | Customer | Support staff | Close; retain messages and audit records |
| Notification | Domain workflow/staff | Recipient marks read; staff retry delivery | Retention policy only |
| Audit event | Server workflow | Admin/operations read | Immutable operational history |

### P. Scheduled commands and operational jobs

The project does not require Redis. Use Windows Task Scheduler, a MySQL-backed job runner, or an equivalent controlled scheduler in production. Do not run overlapping copies of the same command.

```powershell
\.venv\Scripts\python.exe manage.py migrate
\.venv\Scripts\python.exe manage.py check
\.venv\Scripts\python.exe manage.py check --deploy
\.venv\Scripts\python.exe manage.py release_expired_reservations
\.venv\Scripts\python.exe manage.py process_refunds --limit 50
\.venv\Scripts\python.exe manage.py process_notification_queue --limit 200
\.venv\Scripts\python.exe manage.py collectstatic --noinput
\.venv\Scripts\python.exe manage.py test --keepdb
```

Use `seed_role_accounts`, `seed_products`, `seed_vendors`, `seed_healthcare`, and `seed_large_demo_data` only for local/demo data. Never use demo credentials, synthetic licences, fake patient reports, synthetic payment references, or seed images as production evidence.

### Q. Deployment and data protection checklist

Before public launch:

1. Set `DEBUG=False` and configure exact `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`.
2. Enable HTTPS redirect, secure session cookies, secure CSRF cookies, HSTS, and trusted proxy settings appropriate to the hosting topology.
3. Use a dedicated MySQL user; do not use `root`.
4. Configure a strong Django secret key and a valid field-encryption key.
5. Configure private S3-compatible storage for prescriptions, reports, credentials, support attachments, and signed access.
6. Configure malware scanning, image validation, file-size limits, backups, retention, and restore drills.
7. Configure SMTP, Razorpay live/test keys, webhook secret, payment reconciliation, refund policy, and chargeback ownership.
8. Configure courier, lab, doctor consultation, monitoring, uptime, error tracking, and alerting providers or approved manual runbooks.
9. Obtain legal review for pharmacy, prescription, telemedicine, DPDP/privacy, GST/tax, consumer protection, medical-device, and retention requirements.
10. Create named admin, pharmacist, compliance, operations, warehouse, delivery, support, lab, and doctor accounts using least privilege.
11. Run migrations, deployment checks, tests, smoke checks, payment-webhook tests, private-media tests, accessibility tests, backup validation, and restore drills.

### R. Current verified checks and known boundaries

The current codebase passes Django system checks, migration consistency checks, Python compilation, and the complete automated suite available in the repository. The automated suite covers authentication identifiers, MFA, permissions, product trust controls, prescription review, healthcare workflows, Razorpay verification, returns, private media, and industrial hardening.

The following are still implementation boundaries or review items and must not be described as fully production-complete merely because models or screens exist:

- Admin bulk order actions and generic Operations Center forms need to use the same domain transition services as delivery/payment/return workflows.
- COD delivery needs a cash-collection and reconciliation step before payment status is considered settled.
- Tax, handling, platform, and cold-chain invoice charges require approved business rules and calculation code; the current invoice fields alone do not establish a tax implementation.
- Pharmacist private prescription-document access must remain aligned with the pharmacist review capability.
- Consultation payments, video/chat provider integration, refunds, follow-up enforcement, and signed e-prescription operations require provider and clinical policy decisions.
- Courier tracking, NDR/RTO, reverse pickup, cash reconciliation, lab partner integration, email delivery, monitoring, malware scanning, and production object storage require external setup.
- Legal, clinical, pharmacy, tax, privacy, and consumer-policy review cannot be replaced by application code or seed data.

### S. How to investigate a feature or bug

For any feature, trace it in this order:

1. URL in `MediMart/urls.py` and the owning app's `urls.py`.
2. View authorization decorator and capability check.
3. Form fields and `clean()` validation.
4. Model constraints, `save()`, and related records.
5. Transaction boundaries and locking around money, inventory, or capacity.
6. Audit event, status history, notification, and email-delivery creation.
7. Template action and JavaScript request.
8. Automated tests for both allowed and denied actors.
9. Scheduled command or provider webhook needed to finish the lifecycle.

A feature is operationally complete only when the customer-facing action, staff action, authorization, validation, database state, audit/history record, notification, failure path, retry path, and tests all agree.

## Additive UI, Authentication, and Verification Update

This update records the latest implemented changes without removing or replacing the earlier system-guide content.

### Google Authenticator QR enrollment

Two-factor authentication now provides a standards-compatible QR code for Google Authenticator and other TOTP applications.

1. An authenticated user opens **Profile -> Two-factor authentication**.
2. MediMart creates or reuses the short-lived enrollment secret stored in the session.
3. The server generates an `otpauth://totp/MediMart/...` provisioning URI and renders it as an inline SVG QR image.
4. The QR image is not written to media storage, the database, logs, JavaScript, or API responses.
5. The user scans the code, enters the current six-digit code, and submits the enable form.
6. The encrypted MFA secret is stored on the user profile only after the code is verified.
7. The manual setup key and provisioning URI remain available as a fallback when scanning is not possible.

The QR encoder dependency is `qrcode==8.2` in `requirements.txt`. Disabling MFA still requires the current account password and a valid authenticator code. Login MFA uses the existing short-lived pending session and password-change invalidation checks.

### Registration and guest navigation UI

Customer registration and professional registration use the shared responsive authentication layout. The latest registration CSS keeps form fields, password controls, role selection, error text, and action buttons inside their cards across desktop, tablet, and mobile widths.

Unauthenticated navbar actions are represented by the `Sign in` link and the `Create account` dropdown. Both controls are now non-wrapping, have stable minimum widths, keep the dropdown arrow aligned, and become full-width aligned actions when the responsive navbar menu is open. The CSS cache version is incremented in `templates/base.html` whenever these shared styles change.

### Catalogue card layout correction

Product cards now use a constrained action grid. The `View details` action is flexible and ellipsis-safe, while seller comparison, product comparison, and save-for-later controls use bounded widths. This prevents the final quick-action button from being clipped in four-column desktop catalogue layouts or narrow mobile cards.

### Homepage hero typography

The homepage hero heading is intentionally smaller and lighter than the original display treatment. The final override uses a responsive maximum size, `font-weight: 600`, adjusted letter spacing, and a dedicated mobile size so the headline remains prominent without overpowering the hero image or supporting copy.

### Latest verification

- Django system check passes with no issues.
- Focused registration and marketplace tests pass: 45 tests, no failures.
- MFA QR enrollment tests pass, including inline SVG and `otpauth://totp/MediMart` validation.
- The broader project suite previously passed with 111 tests, no failures.
- No database migration is required for the QR, navbar, catalogue-card, or typography changes.

### Current delivery-dashboard permission clarification

The delivery dashboard capability is available to Admin, Operations Manager, Warehouse Manager, and Delivery Staff. Delivery Staff remain restricted to assigned delivery work and allowed last-mile transitions. Operations and warehouse roles can access the operational view needed for assignment, dispatch, inventory, and fulfilment coordination according to their capabilities.

## Additive Current-State and Data-Entry Update (2026-10-12)

This section is an additive correction and expansion of the guide. It records the current roles, capability ownership, management sections, data dependencies, and recommended data-entry order. Earlier sections remain valid unless the source code has changed after this date.

### Complete role inventory

The `UserProfile.Role` choices currently include all of the following roles:

- `customer`: shopping, addresses, prescriptions, healthcare records, bookings, orders, reviews, notifications, and support.
- `vendor`: approved healthcare seller operations, offers, stock, and fulfilment visibility.
- `manufacturer`: equipment and manufactured-product submissions, offers, and evidence.
- `pharmacy`: medicine seller workflows subject to pharmacy and drug-sale licence review.
- `pharmacist`: prescription validation, prescription approval, partial approval, clarification, substitution review, and dispensing records.
- `phlebotomist`: lab collection operations, sample collection, identity/OTP workflows, and lab booking operations.
- `doctor`: verified doctor profile and consultation workspace.
- `delivery_staff`: assigned delivery work and permitted delivery status transitions.
- `support_staff`: support tickets, customer communication, quality complaints, notifications, returns, and service follow-up.
- `compliance_officer`: seller, licence, regulated product, recall, and compliance review.
- `catalog_manager`: categories, brands, products, seller offers, catalogue content, and health guides.
- `operations_manager`: cross-functional operational management and coordination.
- `warehouse_manager`: warehouses, inventory batches, stock, temperature logs, shipments, and fulfilment.
- `admin`: complete custom Operations Center access and, when also a Django superuser, Django Admin access.

The role is stored on `accounts.UserProfile`. A Django superuser is separate from the MediMart role and bypasses the normal capability role mapping. Superuser access should be limited to trusted administrators.

### Complete capability ownership

The capability layer in `accounts/permissions.py` currently maps as follows:

| Capability | Permitted roles |
| --- | --- |
| `dashboard.operations` | Admin, Operations Manager, Compliance Officer, Catalog Manager, Warehouse Manager, Support Staff, Pharmacist, Phlebotomist |
| `dashboard.delivery` | Admin, Operations Manager, Warehouse Manager, Delivery Staff |
| `users.manage` | Admin, Operations Manager |
| `catalog.manage` | Admin, Operations Manager, Catalog Manager |
| `seller.manage` | Admin, Operations Manager, Compliance Officer |
| `compliance.review` | Admin, Operations Manager, Compliance Officer |
| `fulfillment.manage` | Admin, Operations Manager, Warehouse Manager |
| `clinical.manage` | Admin, Operations Manager, Pharmacist, Phlebotomist |
| `clinical.prescription_review` | Admin, Operations Manager, Pharmacist |
| `clinical.lab_operations` | Admin, Operations Manager, Phlebotomist |
| `clinical.doctor_operations` | Admin, Operations Manager |
| `support.manage` | Admin, Operations Manager, Support Staff |
| `finance.manage` | Admin, Operations Manager |
| `audit.view` | Admin, Operations Manager |

Per-user `UserCapabilityOverride` records can grant or deny a capability. An override is audited with its reason and granting user. This is useful for temporary delegation, but it should not replace a clearly assigned primary role.

### Complete Operations Center management directory

The Operations Center is available at `/admin-dashboard/`. Its management URL pattern is:

`/admin-dashboard/manage/<section>/`

The current sections are:

- `users`: user accounts, role, email, password reset, and activation.
- `products`, `categories`, `brands`: catalogue master data and publication state.
- `vendors`, `licenses`, `offers`: sellers, licence evidence, seller offers, approvals, and seller status.
- `orders`, `payments`, `refunds`, `returns`: order operations, payment records, refund records, return requests, and customer outcomes.
- `warehouses`, `inventory`, `temperature_logs`, `shipments`: warehouse, batch, cold-chain, stock, shipment, and delivery operations.
- `prescriptions`, `pharmacists`, `dispensing`: clinical review, pharmacist records, and batch-level dispensing records.
- `doctors`, `consultations`: doctor verification and consultation operations.
- `lab_partners`, `lab_tests`, `lab_slots`, `lab_bookings`: lab catalogue, partners, collection capacity, and booking operations.
- `coupons`: discount rules and coupon activation.
- `recalls`, `quality_complaints`: product/batch recall and quality complaint workflows.
- `blog_categories`, `blog`: health-guide categories and medically reviewed editorial content.
- `support`, `notifications`, `notification_deliveries`: customer support, in-app notices, and email delivery attempts.
- `audit`: immutable operational audit records for permitted users.

Some advanced child records are intentionally available through Django Admin at `/admin/` rather than the custom directory. These include product images, variants, specifications, clinical profiles and interactions, lab branches and reference ranges, sample events and report values, consultation messages and follow-ups, invoice/settlement/dispute records, payment events, inventory movements, and review moderation records.

### Recommended data-entry order

Enter data in dependency order. This avoids orphan records, invalid foreign-key choices, and publishing an unreviewed regulated item:

1. Configure `.env`, connect MySQL on port `3306`, run migrations, and create a trusted superuser.
2. Create staff accounts and assign their `UserProfile` roles. Create separate pharmacist, compliance, warehouse, delivery, lab, doctor, support, and operations accounts.
3. Add top-level and child categories, then brands.
4. Add sellers, pharmacies, manufacturers, and their business licence records and private evidence.
5. Review and verify seller licences before approving regulated sellers.
6. Add products with SKU, category, brand, pricing, images, composition, safety class, regulatory schedule, prescription rules, storage, and recall defaults.
7. Add product images, variants, specifications, clinical profiles, interactions, substitutes, and product questions through Django Admin where required.
8. Add seller offers for products, including seller price, stock, delivery promise, warranty, and offer text. Approve offers only after seller and licence review.
9. Add warehouses and inventory batches with batch number, quantity, MRP, supplier, manufacture/expiry dates, pharmacy/warehouse, and cold-chain requirements.
10. Add pharmacist profiles and verify registration and pharmacy details.
11. Add lab partners, branches, accreditation, service pincodes, tests/packages, images, report SLAs, reference ranges, and collection slots.
12. Add doctor profiles, credentials, specialties, languages, fees, availability, leave, and follow-up rules. Verify credentials before public listing.
13. Add coupons, care plans, health-guide categories, approved health guides, and homepage/content data.
14. Add delivery staff, courier configuration, warehouse assignments, and operational delivery policies.
15. Test customer registration, address selection, prescription upload, pharmacist review, cart, coupon, Razorpay test payment, webhook, invoice, delivery assignment, return, refund, lab booking, and consultation flows.

### Product data checklist

Each published product should have, where applicable:

- Unique SKU, name, category, brand, product type, primary image, gallery images, short description, and full description.
- MRP, selling price, tax configuration, pack size, unit, barcode, manufacturer, composition, strength, dosage form, route, therapeutic class, chemical class, and country of origin.
- Product variants for pack size, strength, flavour, form, or colour.
- OTC/prescription/controlled safety classification, Schedule H/H1/NDPS/habit-forming/state-restricted schedule, state restrictions, quantity limit, minimum shelf life, cold-chain flag, and pharmacist-review flag.
- Storage instructions, warranty where relevant, returnability, delivery promise, seller offers, expiry/batch data, and approved alternatives.

Schedule X and prohibited products are not normal catalogue items: the product model forces them inactive. Prescription, controlled, and scheduled products require the appropriate prescription and pharmacist workflow.

### Seller and licence checklist

Do not mark a seller or licence verified only because a form was submitted. A reviewer should record the legal name, licence type, licence number, issuing authority, premises, state, issue date, expiry date, document, verification source, decision, reviewer, timestamp, and notes. Seller approval and offer publication are separate decisions.

### Lab data checklist

For every lab partner, enter accreditation, licence, quality document, branch details, operating hours, service-area pincodes, and contact details. For each test or package, enter image, sample type, preparation, what it measures, limitations, included test count, price, MRP, home-collection setting, and report SLA. For every collection slot, enter partner, start/end time, capacity, blackout status, active status, and booked count. Structured report values and reference ranges should be entered only from the verified laboratory source.

### Doctor and consultation data checklist

Doctor data should include identity, registration, qualifications, specialty, languages, gender preference, experience, clinic, consultation mode, fee, availability, leave, queue capacity, credential document, verification status, and renewal date. Consultation messages, attachments, notes, advice, referrals, signed e-prescriptions, payments, cancellations, refunds, and follow-ups are private records and should be created through the consultation workflow or protected Django Admin operations.

### Records that should not be manually fabricated

The following records should normally be generated by real workflows or verified provider events rather than inserted as fake data:

- Orders, order items, stock reservations, payment captures, Razorpay webhook events, settlements, chargebacks, refunds, invoices, and credit notes.
- Customer prescriptions, pharmacist reviews, dispensing records, lab bookings, sample events, medical reports, consultations, doctor notes, and health records.
- Delivery status events, OTP verification, proof of delivery, courier events, returns, recalls, quality complaints, and audit events.

Demo seed commands may create sample records for local testing, but demo users, licences, products, prices, and credentials must be replaced before production.

### Current management and seed commands

Run these only after MySQL is configured and migrations are complete:

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_role_accounts
python manage.py ensure_demo_roles
python manage.py seed_products
python manage.py seed_vendors
python manage.py seed_coupons
python manage.py seed_healthcare
```

These seed commands are intended to be repeatable local-development helpers. `seed_vendors` also seeds products and creates demo approved seller offers. `reset_demo_data --confirm-reset` is destructive and is for local development only; it must not be run against production data.

`seed_role_accounts` creates the requested 137 local role accounts, including four pharmacists and four phlebotomists, and writes the usernames and new-account password to the ignored `ROLE_ACCOUNT_CREDENTIALS.md` file. It reuses accounts by username and does not change existing passwords on later runs. The generated password is for local development only.

Scheduled operational commands are separate from master-data entry:

```powershell
python manage.py release_expired_reservations
python manage.py process_refunds --limit 50
python manage.py process_notification_queue --limit 200
```

Because Redis is intentionally excluded, scheduled commands should be run with Windows Task Scheduler or another controlled scheduler. Do not run overlapping copies of the same job.

### Data and integration readiness boundaries

The application can store internal catalogue, users, roles, seller reviews, prescriptions, labs, doctors, orders, returns, refunds, notifications, and audit data without every external provider being connected. Genuine production operation still requires real and approved:

- Razorpay live credentials and webhook secret.
- Courier account, tracking, NDR/RTO, delivery-proof, and reverse-pickup integration or an approved manual process.
- Lab partner accreditation, branch/service data, result workflow, and either API access or a documented manual process.
- Doctor consultation provider or approved chat/video workflow.
- Private object storage and signed URLs for sensitive documents.
- SMTP credentials for transactional email.
- Monitoring, uptime alerts, backups, restore drills, legal review, privacy/consent wording, tax rules, return/refund policy, and named operational owners.

Until these inputs are supplied, keep the relevant records in test/manual-review states and do not present demo licences, demo providers, demo health reports, or test payment credentials as production data.

### Large local demo dataset

For local QA, the project includes a repeatable large-data command:

```powershell
python manage.py seed_large_demo_data
```

The default run creates synthetic records linked to the seeded role accounts, including 1,000 catalogue products, seller offers, images, variants, clinical catalogue fields, inventory batches, 1,200 orders, payments, tracking events, 600 prescriptions, 600 lab bookings, 600 consultations, reviews, returns, refunds, credit notes, settlements, support tickets, notifications, search history, health records, reminders, and audit events. Optional controls are available with `--products`, `--orders`, `--reviews`, and `--notifications`.

The command reuses records identified by `DEMO` markers and does not delete existing application data. It also downloads a small set of public Unsplash healthcare images into the ignored `media/demo-seed/` directory; the sources are recorded in `media/demo-seed/IMAGE_SOURCES.md`. These records, images, licences, clinical profiles, reports, payment references, and provider events are synthetic local-development data only. They must not be presented as real evidence or used for production healthcare operations.

### Prescription image replacement and Care Plan removal

The Care Plan feature was intentionally removed from the active application on 2026-10-13. Its customer route, dashboard tile, home-service tile, admin registrations, seed logic, templates, and database tables are removed by `healthcare.0007_remove_care_plan_models`. Older migration history and older planning notes may still mention Care Plan for historical context; no active runtime code should import or expose it.

To replace existing prescription attachments with supplied private images, run the repeatable command with the four source files:

```powershell
python manage.py replace_prescription_images `
  "C:\path\to\prescription-1.jpg" `
  "C:\path\to\prescription-2.webp" `
  "C:\path\to\prescription-3.jpg" `
  "C:\path\to\prescription-4.jpg"
```

The command stores copies through the configured private media storage and assigns them round-robin to existing prescription records. It never writes to or deletes the public `static/` directory. Prescription records remain protected by the existing owner/reviewer authorization checks.

