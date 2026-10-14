# ReceiptLedger – Web Dashboard & Monorepo Backend Integration Guide

**Document Version:** 1.0.0  
**Target Audience:** Web Dashboard Developer (Iman Hussain) & Core Team  
**Architecture:** Monorepo (`backend/`, `mobile/`, `web/`)  
**Backend Gateway:** FastAPI (Port `8000`)  
**Interactive API Docs (Swagger):** `http://localhost:8000/docs`  

---

## 1. Monorepo Overview & Shared Backend Architecture

`ReceiptLedger` is organized as a unified monorepo where a single FastAPI backend serves both client applications:
1. **Flutter Mobile App (`mobile/`)**: Image capture, edge deskewing, dual OCR submission.
2. **React/Vite Web Dashboard (`web/`)**: Real-time spending analytics, KPI cards, category donuts, multi-month velocity graphs, and the human-in-the-loop Review Queue.

```
ReceiptLedger/ (Monorepo Root)
├── backend/                  ◄── UNIFIED BACKEND REST API (FastAPI)
│   ├── app/
│   │   ├── api/
│   │   │   ├── dashboard.py   ◄── Dedicated Dashboard Endpoints (Groundwork)
│   │   │   ├── analytics.py   ◄── Monthly aggregation, trends, receipts ledger
│   │   │   ├── review_queue.py◄── Human-in-the-loop resolution
│   │   │   ├── receipts.py    ◄── Ingestion & OCR
│   │   │   └── health.py      ◄── Health check
│   │   ├── core/
│   │   │   ├── models.py      ◄── Pydantic Request/Response schemas
│   │   │   └── config.py      ◄── Settings, CORS, & Environment
│   │   └── services/
│   │       └── store.py       ◄── Store abstraction (In-memory / Supabase)
├── mobile/                   ◄── Flutter Mobile Client (Android APK / iOS)
├── web/                      ◄── React + Vite Dashboard Client
└── docs/                     ◄── Specifications & Guides
```

---

## 2. Running the Backend for Dashboard Development

### Step 1: Launch Backend
From the root directory or `backend/`:
```bash
# Option A: Using the Windows batch script
run_backend.bat

# Option B: Direct uvicorn
cd backend
.venv\Scripts\uvicorn app.main:app --reload --port 8000 --host 0.0.0.0
```

### Step 2: Auto-Seeded Demo Data
In `development` mode, the backend **automatically seeds realistic retail receipts and review queue candidates** on initial boot if the store is empty.
This means you do **not** need to manually photograph receipts or run OCR pipelines just to develop charts, donut distributions, or review tables!

You can also trigger re-seeding or reset anytime via API:
* `POST /api/v1/dashboard/seed-demo`
* `POST /api/v1/dashboard/reset`

---

## 3. Dedicated Dashboard Groundwork Endpoints

All endpoints are mounted with prefix `/api/v1`.

### 3.1 Consolidated Dashboard Overview (`GET /api/v1/dashboard/overview`)
Provides all top-level summary data in a single optimized response to eliminate waterfall network requests on page load.

* **URL:** `/api/v1/dashboard/overview?year=2026&month=10` *(parameters optional; defaults to current month)*
* **Sample Response:**
```json
{
  "period": "2026-10",
  "year": 2026,
  "month": 10,
  "total_spend": 12590.0,
  "delta_previous_month": 3840.0,
  "delta_percentage": 43.9,
  "receipt_count": 5,
  "pending_review_count": 2,
  "verified_items_count": 13,
  "stat_cards": [
    {
      "key": "total_spend",
      "label": "Monthly Expenditure",
      "value": 12590.0,
      "formatted_value": "PKR 12,590.00",
      "change": 3840.0,
      "change_type": "increase",
      "helper_text": "+43.9% vs previous month"
    },
    {
      "key": "receipt_count",
      "label": "Ingested Receipts",
      "value": 5,
      "formatted_value": "5",
      "change": 3,
      "change_type": "increase",
      "helper_text": "2 receipts in prior month"
    },
    {
      "key": "pending_reviews",
      "label": "Pending Verification",
      "value": 2,
      "formatted_value": "2",
      "change": null,
      "change_type": "increase",
      "helper_text": "Human-in-the-loop review queue items (< 85% confidence)"
    },
    {
      "key": "avg_ticket",
      "label": "Average Receipt Value",
      "value": 2518.0,
      "formatted_value": "PKR 2,518.00",
      "change": null,
      "change_type": "neutral",
      "helper_text": "Per transaction average"
    }
  ],
  "category_breakdown": [
    {
      "category_name": "Utilities & Bills",
      "color_hex": "#F59E0B",
      "description": "Electricity, gas, water, and top-up bills",
      "total_spend": 5840.0,
      "item_count": 1,
      "percentage_of_total": 46.4
    },
    {
      "category_name": "Groceries & Food",
      "color_hex": "#10B981",
      "description": "Staples, dairy, flour, produce, and fresh meat",
      "total_spend": 4500.0,
      "item_count": 7,
      "percentage_of_total": 35.7
    },
    {
      "category_name": "Household & Cleaning",
      "color_hex": "#3B82F6",
      "description": "Detergents, cleaning supplies, and paper goods",
      "total_spend": 950.0,
      "item_count": 2,
      "percentage_of_total": 7.5
    },
    {
      "category_name": "Personal Care",
      "color_hex": "#8B5CF6",
      "description": "Toiletries, skincare, and hygiene essentials",
      "total_spend": 760.0,
      "item_count": 2,
      "percentage_of_total": 6.0
    },
    {
      "category_name": "Snacks & Beverages",
      "color_hex": "#EC4899",
      "description": "Confectionery, soft drinks, tea, and bakeries",
      "total_spend": 300.0,
      "item_count": 1,
      "percentage_of_total": 2.4
    }
  ],
  "recent_receipts": [ ... ]
}
```

---

### 3.2 Category Metadata & Palette (`GET /api/v1/dashboard/categories`)
Returns all official categories with UI color tokens (`#10B981`, `#3B82F6`, etc.), descriptions, item count, and lifetime spend.

### 3.3 Multi-Month Spending Trends (`GET /api/v1/analytics/trends?months=3`)
Used for the multi-month Category Spend Velocity line chart.
* **Query Params:** `months` (integer, 1-12, default `3`)
* **Returns:** Rolling time-series data with category subtotals per month.

### 3.4 Historical Receipt Ledger (`GET /api/v1/analytics/receipts`)
Used for the searchable, paginated data grid.
* **Query Params:**
  * `page` (default: `1`)
  * `page_size` (default: `20`, max `100`)
  * `search` (optional substring filter against `merchant_name`)
* **Returns:** `{ total: int, page: int, page_size: int, receipts: [ { id, merchant_name, receipt_date, total_amount, line_items: [ ... ] } ] }`

### 3.5 Review Queue Endpoints
* **`GET /api/v1/review-queue?status_filter=UNRESOLVED`**: Returns all low-confidence candidate items waiting for reviewer confirmation.
* **`PATCH /api/v1/review-queue/{queue_id}`**: Submit reviewer confirmation/edit.
  * **Payload:**
    ```json
    {
      "confirmed_name": "Cooking Oil 1L",
      "confirmed_quantity": 1.0,
      "confirmed_unit": "ltr",
      "confirmed_unit_price": 530.0,
      "confirmed_total_price": 530.0,
      "action": "ACCEPTED"
    }
    ```
* **`GET /api/v1/dashboard/review-summary`**: Status badge counts (`unresolved`, `accepted`, `edited`, `total`).

---

## 4. How to Add New Dashboard Endpoints (3 Easy Steps)

When you need a new query or aggregate for a new dashboard widget:

### Step 1: Define Schema in `backend/app/core/models.py`
```python
class MyNewWidgetResponse(BaseModel):
    widget_title: str
    data_points: List[float]
```

### Step 2: Implement Query in `backend/app/services/store.py`
```python
def get_my_widget_data() -> Dict:
    # Query in-memory dicts or Supabase
    return {"widget_title": "Velocity", "data_points": [10.0, 20.0]}
```

### Step 3: Add Route in `backend/app/api/dashboard.py`
```python
@router.get("/dashboard/my-widget", response_model=MyNewWidgetResponse, tags=["Dashboard"])
async def get_my_widget():
    return store.get_my_widget_data()
```
It immediately becomes available under `/api/v1/dashboard/my-widget` and auto-documents in Swagger!

---

## 5. Web Client Configuration (`web/`)

In `web/.env`:
```env
VITE_API_URL=http://localhost:8000
```

In `web/vite.config.js` (Optional proxy configuration to avoid CORS issues entirely):
```javascript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
```
