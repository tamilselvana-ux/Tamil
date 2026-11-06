# AVT - FLOWER MERCHANT & COMMISSION AGENT
## Google Sheets & Drive OAuth 2.0 Per-Merchant Provisioning Engine

### Objective:
Implement automated Google Drive folder & Google Spreadsheet provisioning upon Super Admin merchant approval, authorize using Admin's Google OAuth 2.0 offline credentials (encrypted refresh token), store the dedicated Google Sheet ID per shop, and provide a secure, rate-limited per-merchant data access layer with formula-injection sanitization.

---

### Implementation Task List:
- [x] **Item 01 · Step 1: Discovery & Architecture Specification**
  - Where: `docs/GOOGLE_SHEETS_ARCHITECTURE.md`, `TODO.md`
  - Acceptance:
    - Analyze current registration flow, user model, approval flow, and settings.
    - Define per-merchant spreadsheet workbook schema (`Profile`, `Suppliers`, `Flowers`, `Purchases`, `Postings`).
    - Identify configuration parameters, encryption strategy, and open questions.
  - Status: ✅ (Discovery completed, architecture specified)
- [x] **Item 02 · Step 2: Google Cloud Setup Guide Markdown Documentation**
  - Where: `docs/GOOGLE_CLOUD_SETUP_GUIDE.md`
  - Acceptance:
    - Write complete, click-by-click instructions for creating GCP project, enabling Sheets & Drive APIs, configuring OAuth consent screen, generating Web Client credentials, and configuring environment variables.
  - Status: ✅ (Guide authored with step-by-step instructions, Fernet key generation, and .env template)
- [x] **Item 03 · Step 3: Admin OAuth 2.0 Authorization & Encrypted Token Storage**
  - Where: `apps/accounts/models.py`, `apps/core/google_auth.py`, `apps/accounts/views.py`, `config/urls.py`
  - Acceptance:
    - Model `GoogleAdminCredential` storing encrypted refresh token using Fernet at rest.
    - Admin routes `/super-admin/google/connect/` and `/super-admin/google/callback/` with `access_type=offline` and `prompt=consent`.
    - Auto-refresh mechanism, error handling for revoked tokens, and connection status badge in Super Admin dashboard.
  - Status: ✅ (Implemented encrypted token model, OAuth routes, auto-refresh, and verified with 9 automated tests)
- [x] **Item 04 · Step 4: Merchant Approval & Automated Sheet Provisioning**
  - Where: `apps/accounts/models.py`, `apps/core/google_sheets_provisioner.py`, `apps/accounts/views.py`, `templates/accounts/super_admin.html`
  - Acceptance:
    - Add `google_sheet_id`, `google_sheet_url`, `google_folder_id` and status `APPROVED_SHEET_PENDING` to `ShopProfile`.
    - Idempotent `provision_merchant_sheet(profile_id, admin_user)`: finds/creates folder, creates sheet, moves to folder, seeds tabs (`Profile`, `Suppliers`, etc.), updates status.
    - Failure fallback sets `APPROVED_SHEET_PENDING` with one-click "Retry Sheet Creation" in Super Admin dashboard.
  - Status: ✅ (Provisioner created with formula sanitization, retry endpoint, UI badge & actions; verified with unit tests)
- [x] **Item 05 · Step 5: Per-User Sheet Data Access Layer (`UserSheetService`)**
  - Where: `apps/core/google_sheets_service.py`
  - Acceptance:
    - `UserSheetService` strictly scoped to caller's `request.shop.shopprofile.google_sheet_id`.
    - Formula injection defense: prefix values starting with `=`, `+`, `-`, `@` with `'`.
    - Exponential backoff retry handler for 429/5xx rate limits with batch update optimization.
  - Status: ✅ (Implemented UserSheetService with CRUD methods, deep formula sanitization, and exponential backoff retry handler)
- [x] **Item 06 · Step 6 & 7: Audit Logging, Automated Tests & Verification**
  - Where: `apps/accounts/models.py`, `tests/test_google_sheets_provisioning.py`, `tests/test_google_sheets_service.py`
  - Acceptance:
    - Model `GoogleProvisioningAuditLog` recording actions, timestamps, and sheet IDs (no secret leakage).
    - Unit test suite mocking Google APIs covering OAuth encryption, idempotent sheet creation, retry on failure, formula sanitization, and tenant isolation.
    - Ensure 100% test pass rate across entire application (72 tests passing).
  - Status: ✅ (72 unit and integration tests passing; comprehensive audit logging; zero stub blockers)
