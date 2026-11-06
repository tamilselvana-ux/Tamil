# AVT Flower Merchant & Commission Agent
## System Hardening & Technical Verification Report

**Date of Audit:** 2026-11-05  
**Codebase:** Django Commission-Agent Billing Application (Flower Market)  
**Database:** SQLite (development default) / PostgreSQL (via `DATABASE_URL` env var)  
**Test Suite:** Django `TestCase` (22 automated tests, 100% passing)

---

### 1. Executive Summary

The application has been hardened from an unauthenticated Google Sheets prototype into a multi-tenant, production-grade Django web application. It enforces tenant isolation across all models, utilizes Django's native authentication framework with password hashing and approval gating, eliminates `@csrf_exempt` across all business views, and runs atomic, race-safe billing cutoff logic using database transactions and row locks.

---

### 2. Verified Technical Changes

#### Step 1: Database & ORM Layer
- Replaced Google Sheets/JSON layer (`apps/core/gsheet_db.py`, `gspread`, `google-auth`) with Django ORM models:
  - `Shop` (`apps/shops/models.py`): Tenant root entity with unique shop code.
  - `ShopProfile` (`apps/accounts/models.py`): Gating model (`PENDING`, `APPROVED`, `REJECTED`, `DEACTIVATED`) tied to Django's built-in `User`.
  - `Supplier`, `Area`, `LedgerGroup` (`apps/parties/models.py`): Accounting master entities scoped by `shop`. Tracks `adv_opening`, `advances_given`, `advances_recovered`, and computed `outstanding_advance`.
  - `Flower` (`apps/flowers/models.py`): Master catalog with default rates scoped by `shop`.
  - `PurchaseLot`, `Posting` (`apps/purchases/models.py`): Trading lots and cutoff settlement statements with `select_for_update` locking.
- Abstract tenant base model (`TenantModel`) with `TenantManager` and `TenantQuerySet.for_shop()` helper.
- Database configured via `dj-database-url` supporting PostgreSQL (`DATABASE_URL`) with fallback to local SQLite.
- Seed command: `python manage.py seed_demo` populates demo tenants (`shop-avt-001`, `shop-maha-002`), suppliers, flowers, and lots.

#### Step 2: Authentication, Authorization & Security
- Real session-based Django authentication with hashed passwords (`django.contrib.auth`).
- Registration gate: New shops start in `PENDING` state and cannot access terminal or APIs until approved by a superuser.
- `@shop_required` decorator checks login and `ShopProfile.STATUS_APPROVED` on all views/APIs except public endpoints (`/login/`, `/register/`, `/pending/`, `/health/`).
- Superuser-only protection on `/super-admin/` and `/api/super-admin/update-status/`.
- All `@csrf_exempt` decorators removed. Frontend templates transmit CSRF tokens via `X-CSRFToken` header.
- Settings hardened: `SECRET_KEY` fails fast when `DEBUG=False`, `ALLOWED_HOSTS` defaults to `localhost`, modern `STORAGES` configuration, `AUTH_PASSWORD_VALIDATORS` enabled, IP-based cache rate limiter on login attempts.

#### Step 3: Tenant Isolation & Supplier Resolution
- Model CRUD operations strictly scoped to `request.user.shopprofile.shop` using `get_object_or_404(Model, pk=..., shop=shop)` and `.for_shop(shop)`.
- Replaced fuzzy supplier search with exact case-insensitive match on `code`.
- Autocomplete search API provided via `/api/parties/autocomplete/?q=...`. Unknown supplier codes return HTTP 400/404, never silent defaults.

#### Step 4: Billing Engine & Cutoff Atomicity
- Calculation Engine: Strictly uses `Decimal` with `ROUND_HALF_UP` (money to 2 decimal places, weights to 3 decimal places).
- Canonical flower market test case verified:
  - Lot 1: 300 kg @ ₹40.00 = ₹12,000.00 (Luggage: 20 boxes @ ₹150 = ₹3,000; Coolie: 20 boxes @ ₹15 = ₹300)
  - Lot 2: 300 kg @ ₹40.00 = ₹12,000.00 (Luggage: 20 boxes @ ₹150 = ₹3,000; Coolie: 20 boxes @ ₹15 = ₹300)
  - Gross Total: ₹24,000.00
  - Commission: 15% of ₹24,000.00 = ₹3,600.00
  - Total Less: ₹3,600 + ₹6,000 (lug) + ₹600 (coolie) = ₹10,200.00
  - Net Balance Payable: ₹24,000 - ₹10,200 = ₹13,800.00
- Opening advance is NOT automatically deducted. Clerk-entered advance is validated against `outstanding_advance` (`0 <= amount <= outstanding_advance`).
- Cutoff Posting: Computed entirely server-side inside `transaction.atomic()` using `select_for_update()`. Assigns race-safe sequential posting number per shop (`0001`, `0002`...) and permanently seals lots.
- Double-billing prevented: sealed lots cannot be selected for subsequent postings.
- Batch Lot Save Atomicity: Validates input (>0 weight, >=0 rates/boxes). Any invalid row triggers rollback of all rows. Posted lots cannot be edited or deleted.
- Invoice & PDF: Generated from saved `Posting` record (or explicitly marked `DRAFT PREVIEW` when unposted).

---

### 3. Automated Test Results

Ran `python manage.py test` across all test modules:
```text
Creating test database for alias 'default'...
......................
----------------------------------------------------------------------
Ran 22 tests in 9.095s

OK
Destroying test database for alias 'default'...
```

#### Test Suite Breakdown:
1. **`tests.test_auth` (7 tests):**
   - `test_anonymous_user_redirected_on_protected_pages` — PASS
   - `test_anonymous_user_denied_on_protected_apis` — PASS
   - `test_pending_shop_user_cannot_access_protected_views` — PASS
   - `test_non_superuser_cannot_access_super_admin` — PASS
   - `test_non_superuser_cannot_approve_shops` — PASS
   - `test_superuser_can_access_super_admin_and_approve_shop` — PASS
   - `test_login_rate_limiting` — PASS
2. **`tests.test_tenant_isolation` (6 tests):**
   - `test_shop_a_cannot_see_shop_b_suppliers_in_autocomplete` — PASS
   - `test_shop_a_cannot_access_shop_b_supplier_detail` — PASS
   - `test_shop_a_cannot_delete_or_modify_shop_b_supplier` — PASS
   - `test_shop_a_cannot_view_or_edit_shop_b_flowers` — PASS
   - `test_shop_a_cannot_view_or_post_shop_b_lots` — PASS
   - `test_shop_a_cannot_view_or_download_shop_b_posting` — PASS
3. **`tests.test_calculations` (3 tests):**
   - `test_sample_result_accounting_verification` — PASS (24000 gross / 3600 comm / 10200 less / 13800 net)
   - `test_decimal_rounding_half_up` — PASS
   - `test_zero_lot_and_zero_boxes` — PASS
4. **`tests.test_billing` (6 tests):**
   - `test_opening_advance_not_auto_deducted` — PASS
   - `test_advance_validation_against_outstanding_balance` — PASS
   - `test_posting_seals_lots_and_prevents_double_billing` — PASS
   - `test_posted_lot_cannot_be_edited` — PASS
   - `test_batch_save_atomicity_rolls_back_on_single_bad_row` — PASS
   - `test_pdf_endpoint_returns_valid_pdf_and_404_for_other_shop` — PASS

---

### 4. Remaining Known Gaps & Production Checklist

Before deploying to a public-facing Internet production server, the following external items must be configured:
1. **PostgreSQL Setup:** Set `DATABASE_URL=postgres://user:password@host:5432/dbname` in `.env` for production workloads.
2. **Secret Key & Security Variables:** Set strong, random strings for `DJANGO_SECRET_KEY` and set `DJANGO_DEBUG=False`.
3. **Admin Contact Number:** Set `ADMIN_CONTACT_NUMBER` in `.env` (displays on `/pending/` screen for onboarding merchants).
4. **Static Files Collection:** Run `python manage.py collectstatic --noinput` during server deployment build.
5. **Reverse Proxy & TLS:** Place Nginx or Caddy in front of Gunicorn/Waitress to terminate TLS (HTTPS) on port 443.
