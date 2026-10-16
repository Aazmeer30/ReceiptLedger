# ReceiptLedger – Admin Operations & Audit Console Specification
**Document Version:** 2.0.0 (Admin & Operations Pivot)  
**Target Audience:** Frontend Team, UI/UX Designer & Autonomous AI Agents  
**Monorepo Location:** `web/` (React 18 + Vite 5)  
**Backend API Gateway:** `http://localhost:8000/api/v1`  
**Swagger Docs:** `http://localhost:8000/docs`

---

## 1. Product Positioning: Mobile App vs. Web Dashboard

To avoid redundant duplicate screens, ReceiptLedger maintains a clean separation of concerns:

| Dimension | Mobile Client (`mobile/` Flutter) | Web Dashboard (`web/` React) |
| :--- | :--- | :--- |
| **Primary User** | End Shopper / Consumer | System Administrator / Auditor / Operator |
| **Form Factor** | Handheld Smartphone (One-thumb) | Desktop / Laptop (Wide Screen & Keyboard) |
| **Primary Workflow**| Camera capture, edge cropping, quick upload | Verification, AI telemetry, audit log, data control |
| **Scope of View** | "My Personal Groceries & Receipts" | "Global Ledger, OCR Engine Health, System Triage" |
| **Cognitive Load** | Low (Fast, automated, minimal typing) | High-Detail (Raw OCR comparison, overrides, overrides) |

---

## 2. Admin Console Screen Architecture (4 Key Workspaces)

The Admin Web Dashboard is structured into 4 purpose-built operational panels:

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ TOP BAR: System Status (Gemini Flash Lite • Cloud Vision Quota • Tesseract • Supabase) │
│          Admin Controls: [Seed Demo Data] [Clear Store] [Export CSV]                  │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 1. TELEMETRY & INGESTION STATS (4 Cards)                                               │
│    • Ingestion Volume (Total Receipts)      • OCR Avg Confidence (e.g. 91.4%)          │
│    • Needs Review Items (Pending Action)    • Handwritten vs Printed Ratio             │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 2. HUMAN-IN-THE-LOOP VERIFICATION DESK (Core Desktop Admin Feature)                    │
│    Side-by-side triage table: Raw OCR candidate vs Clean Canonical item.               │
│    Quick actions: [1-Click Accept (Enter)] [Inline Edit & Save (Ctrl+S)]               │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 3. INGESTION AUDIT & RAW OCR INSPECTOR (Searchable Deep Audit Ledger)                  │
│    Inspect every receipt: Raw OCR tokens, Deduplication Hash status, Engine used.     │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 4. MACRO SPENDING & CATEGORY INTELLIGENCE                                              │
│    High-level category donut & velocity curves across all ingested receipts.           │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Detailed Component Breakdown & API Wiring

### Panel 1: Top Bar & AI Engine Telemetry
* **API:** `GET /api/v1/health`
* **Displays:**
  * **Gemini Vision Status:** Model name (`gemini-3.5-flash-lite`) and latency.
  * **Cloud Vision Quota:** Remaining free-tier API calls.
  * **Local Engines:** Tesseract OCR / EasyOCR availability.
  * **Storage Mode:** `in_memory (dev mode)` or `Supabase (PostgreSQL)`.
* **Action Buttons:**
  * **Seed Demo Data** (`POST /api/v1/dashboard/seed-demo`): Instantly populates realistic receipts and review items.
  * **Reset Ledger** (`POST /api/v1/dashboard/reset`): Clears database for testing zero/empty states.

### Panel 2: Telemetry & Quality KPI Cards
* **API:** `GET /api/v1/dashboard/overview` & `GET /api/v1/dashboard/review-summary`
* **Cards:**
  1. **Total Ingested Volume:** Total receipts processed (`receipt_count`).
  2. **Pending Human Review:** Total flagged items (`unresolved`). Highlighted with amber badge.
  3. **Resolved Items:** Total verified items (`accepted + edited`).
  4. **Global Ledger Spend:** Total PKR value processed across all receipts.

### Panel 3: Human-in-the-Loop Verification Desk (High Priority)
* **APIs:** 
  * `GET /api/v1/review-queue?status_filter=UNRESOLVED`
  * `PATCH /api/v1/review-queue/{queue_id}`
* **Why Desktop?** Mobile users dislike typing corrections on small screens. The Admin desk provides a rapid triage interface:
  * **Columns:**
    * Flagged Timestamp & Merchant Name
    * **Raw OCR Scanned Text** (e.g., `"129728 WITHA PER KG 0.640"`)
    * **Candidate Clean Item** (e.g., `"Sweet Melon"`)
    * **Confidence Pill** (e.g., `74.5%` colored red/amber)
    * **Quantity & Price Inputs** (`0.64 kg`, `PKR 127.36`)
    * **Actions:**
      * **Accept Button (Green):** Dispatches `PATCH /api/v1/review-queue/{id}` with `action: "ACCEPTED"`.
      * **Edit & Confirm Button (Blue):** Submits corrected values with `action: "EDITED"`.
* **Keyboard Flow:** Auto-advances to next review item on submit.

### Panel 4: Ingestion Audit & Raw Text Inspector
* **API:** `GET /api/v1/analytics/receipts?page=1&page_size=25&search={query}`
* **Features:**
  * Search by merchant or date range.
  * Shows receipt type badges: `PRINTED` (Supermarket bill) vs. `HANDWRITTEN` (Bazaar slip).
  * Shows duplicate detection status (`is_duplicate: true/false`).
  * **Expandable Audit Drawer:** Clicking a receipt reveals:
    * Deduplication hashes (perceptual & metadata).
    * Confidence score per individual line item.
    * Category classification chip with backend color token.

### Panel 5: Macro Category Breakdown
* **API:** `GET /api/v1/dashboard/overview`
* **Displays:** Donut chart of global category distribution using official color tokens:
  * Groceries: `#10B981` | Health & Pharmacy: `#06B6D4` | Household: `#3B82F6` | Personal Care: `#8B5CF6` | Utilities: `#F59E0B` | Snacks: `#EC4899` | Misc: `#6B7280`

---

## 4. Copy-Paste AI Agent Prompt for the Web Developer

Give this exact prompt to the AI agent working in the `web/` directory:

```markdown
You are building the Admin Operations & Audit Web Dashboard for ReceiptLedger in `web/` using React 18 and Vite.
The dashboard is an ADMIN / AUDIT CONSOLE, not a personal shopper app.

Backend REST API Base URL: `http://localhost:8000/api/v1`

### Key Requirements:
1. Top Bar:
   - Display system engine chips from `GET /health` (Gemini, Cloud Vision quota, DB mode).
   - Add two action buttons: "Seed Demo Data" (`POST /dashboard/seed-demo`) and "Reset Ledger" (`POST /dashboard/reset`).
2. Telemetry Row:
   - 4 stat cards from `GET /dashboard/overview` and `GET /dashboard/review-summary` (Total Volume, Pending Audit, Verified Items, Total Spend).
3. Human-in-the-Loop Review Desk (Most Important):
   - Table of pending items from `GET /review-queue?status_filter=UNRESOLVED`.
   - Side-by-side display of `raw_text` vs `candidate_name`, quantity, and price.
   - 1-click "Accept" and "Edit & Save" calling `PATCH /review-queue/{id}`.
4. Ingestion Audit Log:
   - Paginated table from `GET /analytics/receipts`.
   - Search filter by merchant name.
   - Expandable rows showing individual line items with confidence badges.
5. Macro Category Donut:
   - Render `category_breakdown` with backend-provided `color_hex` values.

Style with clean, modern dark-mode CSS (slate-900 background, slate-800 cards, crisp typography).
Use simple `fetch()` or `axios`. Include loading spinners and empty states.
```
