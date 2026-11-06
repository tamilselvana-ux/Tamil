# Google Sheets & Google Drive Multi-Tenant Provisioning Architecture

**Date:** 2026-11-05  
**Component:** Multi-Tenant Database Layer via Google Drive & Sheets API  
**Author:** AI Software Company Backend Division  

---

### 1. Discovery Findings: Existing System Analysis

#### 1.1 Registration Flow
- **Location:** [`apps/accounts/views.py`](file:///d:/Bill/apps/accounts/views.py) (`register_view`) & [`templates/accounts/register.html`](file:///d:/Bill/templates/accounts/register.html)
- **Mechanism:** Collects Shop Name, Mandi Address, Owner Username, Phone, Email, and Password.
- **State on Submission:** 
  - Creates a `Shop` instance with unique code `shop-xxxxxxxx`.
  - Creates a Django `User` with hashed credentials.
  - Creates a `ShopProfile` in status `PENDING`.
  - Redirects user to [`/pending/`](file:///d:/Bill/templates/accounts/pending.html), blocking terminal access until approved.

#### 1.2 User & Tenant Models
- **`ShopProfile`** ([`apps/accounts/models.py`](file:///d:/Bill/apps/accounts/models.py)): One-to-one link with Django `User`, foreign key to `Shop`, with `status` (`PENDING`, `APPROVED`, `REJECTED`, `DEACTIVATED`), `phone`, `approved_by`, `approved_at`.
- **`Shop`** ([`apps/shops/models.py`](file:///d:/Bill/apps/shops/models.py)): Multi-tenant anchor (`code`, `name`, `market_address`, `phone`, `email`, `devotional_motto`).

#### 1.3 Super Admin Approval Flow
- **Location:** [`apps/accounts/views.py`](file:///d:/Bill/apps/accounts/views.py) (`super_admin_view`, `update_shop_status_api`) & [`templates/accounts/super_admin.html`](file:///d:/Bill/templates/accounts/super_admin.html).
- **Mechanism:** Strict `request.user.is_superuser` validation. AJAX `POST /api/super-admin/update-status/` toggles status between `APPROVED`, `REJECTED`, `DEACTIVATED`, `PENDING`.

---

### 2. Multi-Tenant Google Drive & Sheets Architecture

```
[ Super Admin / Founder ]
          │ (One-time OAuth 2.0 Web flow)
          ▼
   /super-admin/google/connect/ ────► Google Accounts Consent Screen
          ▲                                    │ (offline access, prompt=consent)
          │                                    ▼
   /super-admin/google/callback/ ◄──── Authorization Code
          │
          ├─► Exchanges Code for Refresh Token + Access Token
          ├─► Encrypts Refresh Token with AES/Fernet (Key in ENV)
          └─► Stores in GoogleAdminCredential model

──────────────────────────────────────────────────────────────────────────

[ Merchant Registration & Automated Sheet Provisioning ]

Farmer / Merchant Registers ────► Shop created (PENDING)
                                            │
Super Admin clicks "Approve" ───────────────┼──────────┐
                                            │          │ (If Google API fails)
                                            ▼          ▼
                       Check Admin OAuth Valid?   status = APPROVED_SHEET_PENDING
                                    │ (Yes)       (Audit log recorded;
                                    ▼              "Retry Sheet Creation" button)
             Find/Create Drive Folder: "App User Sheets"
                                    │
             Create Spreadsheet: "User - {name} ({userId})"
                                    │
             Move Sheet into Drive Folder (addParents / removeParents)
                                    │
             Initialize Pre-formatted Tabs & Headers:
               - Profile (Name, Phone, Email, Market Address, Registered Date)
               - Suppliers (Code, Name, Area, Comm%, Luggage, Advance)
               - Flowers (Code, Name, Default Rate)
               - Purchases (Date, Lot ID, Farmer, Variety, Weight, Rate, Less, Net)
               - Postings (Posting #, Farmer, Dates, Gross, Deductions, Net Balance)
                                    │
             Save sheet_id & sheet_url to ShopProfile
                                    │
             status = APPROVED ────► Merchant can now trade!
```

---

### 3. Proposed Schema for Per-Merchant Spreadsheet

Each newly approved merchant receives their own isolated Google Spreadsheet with 5 formatted tabs:

1. **`Profile` Tab**:
   - `[Field, Value]`
   - Shop Code, Agency Name, Market Stall Address, Contact Number, Email, Approved Date, Super Admin ID.
2. **`Suppliers` Tab**:
   - Headers: `Supplier Code`, `Full Name`, `Procurement Area`, `Ledger Group`, `Commission %`, `Default Luggage Rate`, `Opening Advance (₹)`, `Status`.
3. **`Flowers` Tab**:
   - Headers: `Flower Code`, `Variety Name`, `Default Rate (₹/kg)`, `Unit`, `Status`.
4. **`Purchases` Tab**:
   - Headers: `Date`, `Lot ID`, `Supplier Code`, `Supplier Name`, `Flower Code`, `Flower Name`, `Weight (kg)`, `Rate (₹)`, `Gross Value (₹)`, `Boxes`, `Luggage (₹)`, `Coolie (₹)`, `Net Lot Value (₹)`, `Posting No`.
5. **`Postings` Tab**:
   - Headers: `Posting No`, `Supplier Code`, `Supplier Name`, `From Date`, `To Date`, `Gross Total (₹)`, `Commission (₹)`, `Luggage (₹)`, `Coolie (₹)`, `Advance Deducted (₹)`, `Total Less (₹)`, `Net Balance (₹)`, `Sealed Timestamp`.

---

### 4. Security & Sanitization Specification

1. **Encrypted Token Storage**:
   - The Admin's Google OAuth refresh token is never stored in plain text.
   - Encrypted at rest using `cryptography.fernet.Fernet` with a dedicated key (`GOOGLE_OAUTH_ENCRYPTION_KEY` or derived from `SECRET_KEY`).
2. **Strict Server-Side Isolation**:
   - `UserSheetService` only operates on the `sheet_id` linked to the authenticated user's `ShopProfile`. Client-submitted sheet IDs are completely ignored.
3. **Formula Injection Defense**:
   - Any string value starting with `=`, `+`, `-`, `@`, `\t`, or `\r` is escaped with a leading single quote (`'`) to prevent CSV/Sheet formula execution vulnerabilities.
4. **Rate-Limiting & Exponential Backoff**:
   - Sheets API write quota is capped at 60 requests/minute per user. All writes are batched (`batchUpdate`, `append`) with exponential backoff on HTTP 429 and 5xx errors.

---

### 5. Open Questions & Design Decisions

1. **Google Drive Folder Location**:
   - *Default choice:* The system creates/uses a root folder named `"AVT Flower Market - Merchant Sheets"` in the Admin's Google Drive. (Can be customized via `GOOGLE_DRIVE_FOLDER_NAME` in `.env`).
2. **Merchant Read/Write Access to Google Drive Directly**:
   - *Security recommendation:* Merchants interact with their data exclusively through the high-speed Koyambedu Terminal web app. The sheet is stored privately in the Admin's Drive. If enabled via `GOOGLE_SHEET_SHARE_VIEWER=True`, the sheet will automatically be shared as read-only ("Viewer") with the merchant's registered Gmail ID.
3. **Primary Database vs. Sheet Dual-Write**:
   - *Architecture recommendation:* SQLite/PostgreSQL remains the high-speed local transactional engine with instant sub-millisecond ACID writes; the Google Sheet acts as the merchant's cloud-synced personal spreadsheet database.
