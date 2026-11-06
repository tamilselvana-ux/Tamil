# AVT Flower Merchant & Commission Agent Billing System

A multi-tenant Django web application designed for commission agents and flower merchants in agricultural produce markets (e.g., Koyambedu Wholesale Flower Market, Chennai).

---

## 🌟 Key Features

- **Multi-Tenant Architecture:** Every shop/merchant has strictly isolated data (parties, flowers, lots, postings) enforced at the ORM layer.
- **Django Authentication & Approval Workflow:** Native session auth with password hashing. New shops register with `PENDING` status and require Super Admin approval before accessing terminal views.
- **High-Speed Purchase Trading Terminal:** 11-column high-volume lot entry grid with keyboard shortcuts (`F2` Add Line, `F8` Batch Save, `F10` Cutoff & Bill).
- **Exact Decimal Arithmetic:** Zero floating-point drift. All prices, gross totals, commissions, deductions, and net balances use Python `Decimal` with `ROUND_HALF_UP`.
- **Atomic Cutoff Billing & Lot Sealing:** Concurrency-safe postings inside `transaction.atomic()` with `select_for_update()`. Prevents double-billing and assigns sequential posting numbers per shop.
- **Party & Supplier Master:** Tracks suppliers, default commission %, luggage rates, and live advance balances (`adv_opening + advances_given - recovered`). Opening advances are never auto-deducted.
- **Official Koyambedu Bill PDF Generation:** Produces ReportLab-generated invoices faithfully matching traditional physical market bills.

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- Python 3.10+ (Tested on Python 3.12 / 3.15)
- SQLite (default for development) or PostgreSQL (for production)

### 2. Installation & Setup

```bash
# 1. Clone repository and navigate to root
cd Bill

# 2. Create and activate a virtual environment
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux / macOS:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
# Copy .env.example to .env and adjust if needed:
copy .env.example .env
```

### 3. Database Migration & Seed Demo Data

```bash
# Run Django database migrations
python manage.py migrate

# Seed initial demo shops, users, suppliers, flowers, and lots
python manage.py seed_demo
```

### 4. Running the Development Server

```bash
# Using standard Django runner:
python manage.py runserver 8000

# Or using the custom waitress/production runner:
python run_server.py --port 8000
```
Open your browser at `http://127.0.0.1:8000/`.

---

## 🔑 Seeded Demo Credentials

| Role | Username | Password | Notes |
|---|---|---|---|
| **Super Admin** | `superadmin` | `admin123` | Access `/super-admin/` to approve or reject pending shop accounts |
| **AVT Merchant Owner** | `avt_owner` | `avt123` | Approved shop owner (`shop-avt-001`), access to trading terminal |

---

## 📊 Google Sheets & Drive Per-Merchant Provisioning Engine

The application includes an automated Google Sheets and Google Drive integration that provisions an isolated cloud spreadsheet database for each merchant upon Super Admin approval:

- **Automated Sheet Creation**: When Super Admin approves a registered merchant, the system creates a dedicated Google Spreadsheet inside the Admin's Google Drive folder (`AVT Flower Market - Merchant Sheets`).
- **Standard Tabs Prepopulated**: `Profile`, `Suppliers`, `Flowers`, `Purchases`, and `Postings` with pre-styled headers and sanitized metadata.
- **Strict Tenant Isolation**: `UserSheetService` locks operations exclusively to the authenticated merchant's assigned `google_sheet_id`.
- **Formula-Injection Sanitization**: All cell inputs starting with `=`, `+`, `-`, `@`, `\t`, `\r` are escaped with a leading single quote (`'`).
- **Zero-Downtime Resilience & Exponential Backoff**: API rate limits (HTTP 429) and transient errors (5xx) automatically retry with exponential backoff and jitter. If Google Drive is temporarily unavailable during approval, the merchant is marked `APPROVED_SHEET_PENDING` with a one-click **"Retry Sheet"** button on `/super-admin/`.
- **Token Security**: OAuth 2.0 refresh tokens are stored encrypted at rest using AES-128 (Fernet) in `GoogleAdminCredential`.

📖 Complete Step-by-Step Setup Guide: [`docs/GOOGLE_CLOUD_SETUP_GUIDE.md`](docs/GOOGLE_CLOUD_SETUP_GUIDE.md)

---

## 🧪 Running Automated Tests

Run the full Django test suite:
```bash
python manage.py test
```
The test suite (72+ tests) covers:
- Authentication, role gating, and login rate limiting
- Super Admin approval permissions & OAuth 2.0 connection flows
- Automated Google Drive folder & Google Sheet creation with mocked Google APIs
- UserSheetService tenant isolation, formula sanitization, and exponential backoff retry handler
- Cross-tenant isolation (preventing cross-shop data leaks)
- Exact Decimal calculation engine (including the canonical ₹24,000 / ₹3,600 / ₹10,200 / ₹13,800 test case)
- Advance deduction validation against outstanding balance
- Cutoff lot sealing, race-safe sequential numbering, and double-billing prevention
- Batch save atomicity rollback
- Scoped PDF export generation and 404 security checks

---

## ⚙️ Environment Variables (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_DEBUG` | `True` | Set `False` in production |
| `DJANGO_SECRET_KEY` | *(Dev key)* | Required when `DJANGO_DEBUG=False` |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated allowed domain names / IPs |
| `DATABASE_URL` | *(SQLite)* | `postgres://user:pass@host:5432/dbname` for PostgreSQL |
| `ADMIN_CONTACT_NUMBER` | `""` | Support phone number shown to pending registered merchants |
| `CSRF_TRUSTED_ORIGINS` | `http://127.0.0.1:8000` | Comma-separated trusted origins for CSRF protection |
| `SECURE_SSL_REDIRECT` | `False` | Enforce HTTPS redirect and HSTS headers |
| `FIELD_ENCRYPTION_KEY` | *(Dev default)* | 32-byte URL-safe base64 Fernet key used to encrypt OAuth refresh tokens at rest |
| `GOOGLE_CLIENT_ID` | `""` | GCP OAuth 2.0 Web Application Client ID |
| `GOOGLE_CLIENT_SECRET` | `""` | GCP OAuth 2.0 Web Application Client Secret |
| `GOOGLE_OAUTH_REDIRECT_URI` | `http://127.0.0.1:8000/super-admin/google/callback/` | Authorized OAuth redirect URI matching Google Cloud Console |
| `GOOGLE_DRIVE_FOLDER_NAME` | `AVT Flower Market - Merchant Sheets` | Admin Google Drive parent folder name for merchant sheets |
