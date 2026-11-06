# AVT FLOWER MERCHANT — GOOGLE SHEETS DATABASE DESIGN
**Engine:** Google Sheets (v4 API via `gspread`)  
**Architecture:** Multi-Worksheet Document as a Relational Database  

---

## 1. Google Spreadsheet Structure

A single master Google Spreadsheet (e.g. named `AVT_Flower_Merchant_DB`) contains the following structured worksheets (tabs):

### Tab 1: `Shops`
Stores multi-tenant merchant shop registrations.
| Column | Header | Type | Description |
|---|---|---|---|
| A | `shop_id` | String (UUID) | Unique Tenant ID |
| B | `name` | String | Shop Name (e.g. AVT Flower Merchants) |
| C | `market_address` | String | e.g. FB-78, Kamarajar Market, Koyambedu |
| D | `owner_username`| String | Username of the owner |
| E | `gmail_id` | String | Owner email |
| F | `phone` | String | Owner mobile number |
| G | `status` | String | `PENDING` / `APPROVED` / `REJECTED` / `DEACTIVATED` |
| H | `created_at` | String (ISO) | Registration timestamp |
| I | `approved_by` | String | Admin who approved |

### Tab 2: `Suppliers`
Stores supplier accounts scoped by `shop_id`.
| Column | Header | Type | Description |
|---|---|---|---|
| A | `supplier_id` | String (UUID) | Unique record ID |
| B | `shop_id` | String (UUID) | Tenant Scope |
| C | `code` | String | Supplier Code (e.g. `HMS DPS`) |
| D | `name` | String | Supplier Name (e.g. `HMS DOLL DPS`) |
| E | `ledger_group` | String | e.g. `Suppliers group` |
| F | `ledger_op_bal`| Decimal | Ledger Opening Balance |
| G | `area_name` | String | Procurement belt (Salem, Hoskote, etc.) |
| H | `flower_name` | String | Default flower (Dol Yellow, Paneer, etc.) |
| I | `adv_opening` | Decimal | Advance Opening Balance |
| J | `commission_pct`| Decimal | Agreed Commission % (e.g. 15.00) |
| K | `luggage_default`| Decimal | Luggage rate per box |
| L | `gate_charges` | Boolean | True / False |
| M | `status` | String | `Active` / `Inactive` |
| N | `interest_pct` | Decimal | Interest on advance |

### Tab 3: `Flowers`
Flower catalog and code mappings.
| Column | Header | Type | Description |
|---|---|---|---|
| A | `flower_id` | String (UUID) | Record ID |
| B | `shop_id` | String (UUID) | Tenant Scope |
| C | `code` | String | Short code (e.g. `DOLY`, `PAN`, `SAM`) |
| D | `name` | String | Variety Name (e.g. `DOL YELLOW`, `PANEER`) |
| E | `default_rate`| Decimal | Standard auction rate |

### Tab 4: `Purchases`
Individual flower lots received and entered at the terminal.
| Column | Header | Type | Description |
|---|---|---|---|
| A | `lot_id` | String (UUID) | Transaction row ID |
| B | `shop_id` | String (UUID) | Tenant Scope |
| C | `purchase_date`| Date | Lot arrival date |
| D | `party_code` | String | Supplier Code |
| E | `party_name` | String | Supplier Name |
| F | `flower_code` | String | Flower Code |
| G | `flower_name` | String | Flower Name |
| H | `weight` | Decimal | Weight in kg (3 decimal places) |
| I | `rate` | Decimal | Rate per kg |
| J | `gross_value` | Decimal | `Weight * Rate` |
| K | `boxes` | Integer | Box count |
| L | `lug_rate` | Decimal | Luggage rate per box |
| M | `luggage_amt` | Decimal | `Boxes * Lug_Rate` |
| N | `coolie_rate` | Decimal | Coolie rate per box |
| O | `coolie_amt` | Decimal | `Boxes * Coolie_Rate` |
| P | `net_lot_value`| Decimal | `Gross - Luggage - Coolie` |
| Q | `posting_no` | String | Blank if unbilled, or posting sequence |

### Tab 5: `Postings`
Aggregated supplier billing statements with cutoff dates and deductions.
| Column | Header | Type | Description |
|---|---|---|---|
| A | `posting_id` | String (UUID) | Posting record ID |
| B | `shop_id` | String (UUID) | Tenant Scope |
| C | `posting_no` | String | Sequence (e.g. `0032`) |
| D | `from_date` | Date | Billing start date |
| E | `to_date` | Date | Cutoff date |
| F | `supplier_name`| String | Supplier Name |
| G | `gross_total` | Decimal | Sum of lot gross values |
| H | `commission` | Decimal | Calculated commission deduction |
| I | `total_luggage`| Decimal | Sum of luggage charges |
| J | `total_coolie` | Decimal | Sum of coolie charges |
| K | `total_expense`| Decimal | Miscellaneous expenses |
| L | `adv_deducted` | Decimal | Advance deducted from this bill |
| M | `total_less` | Decimal | Sum of all deductions |
| N | `net_balance` | Decimal | Final balance payable to supplier |
| O | `created_at` | String (ISO) | Timestamp of posting |

---

## 2. Authentication & Credential Setup
1. Place the Google Cloud Service Account JSON key at `credentials/google_sheets_credentials.json`.
2. Share the Google Spreadsheet with the service account email (with `Editor` permissions).
3. Specify `GSHEET_SPREADSHEET_ID` or URL in `.env`.
4. If no credentials file is present, the built-in Local Mirror handles all CRUD operations seamlessly until credentials are connected.
