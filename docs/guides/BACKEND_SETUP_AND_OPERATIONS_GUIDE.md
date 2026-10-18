# ReceiptLedger Backend Setup & Operations Guide

### Comprehensive System Reference & External Service Integration Manual
* **Project:** ReceiptLedger
* **Module:** Backend API Engine (`FastAPI` + `OpenCV` + `OCR Engine Matrix` + `Supabase`)
* **Course:** Software Project Management (SPM-458)
* **Author / Maintainer:** Asad ([@Asad101001](https://github.com/Asad101001))
* **Version:** 1.0.0 (Production & Local Development Ready)

---

## 1. Architecture Overview & Pipeline Topology

The ReceiptLedger backend is the central computational core of the system. It processes raw camera captures and scanned receipts, extracts and normalizes financial records, prevents duplicate expenses, and generates aggregated spending analytics.

```
                      ┌──────────────────────────────────────┐
                      │ POST /api/v1/receipts/upload (image) │
                      └──────────────────┬───────────────────┘
                                         ▼
                             [OpenCV Preprocessing]
                       • Laplacian Blur Variance (≥80)
                       • MinAreaRect Deskewing
                       • CLAHE Contrast Enhancement
                                         │
                                         ▼
                      [Layer 1 Visual Deduplication]
                       • 64-bit DCT pHash via cv2.dct
                       • Hamming Distance Check (≤4)
                           ├── (Match Found) ─────────────► 409 Conflict (Early Exit, 0 OCR Cost)
                           └── (Unique Image) ────────────┐
                                                          ▼
                                            [Receipt Type Classifier]
                                            • Component height CV (cv_h > 1.25)
                                            • Stroke variance analysis
                                                          │
                         ┌────────────────────────────────┴────────────────────────────────┐
                         ▼                                                                 ▼
                 [PRINTED PATH]                                                   [HANDWRITTEN PATH]
          1. Google Cloud Vision (Primary)                                     1. EasyOCR (Primary)
          2. Local Tesseract 5 (Fallback)                                      2. Tesseract 5 (Fallback)
                         │                                                                 │
                         └────────────────────────────────┬────────────────────────────────┘
                                                          ▼
                                            [Spatial Line Reassembly]
                                            • Sweep-line algorithm (y_tolerance = 15px)
                                            • Horizontal ordering (x_min ascending)
                                                          │
                                                          ▼
                                              [NLP Normalization Engine]
                                            • Pakistani Grocery Taxonomy (Urdu/English)
                                            • Levenshtein Fuzzy Matching (≥0.72)
                                            • Regex Price & Unit Extractors
                                                          │
                                                          ▼
                                            [Layer 2 Metadata Deduplication]
                                            • SHA-256 (merchant + date + total_cents)
                                                          ├── (Match Found) ──► 409 Conflict
                                                          └── (Unique) ───────┐
                                                                              ▼
                                                                  [Confidence Evaluation]
                                                      • Mean OCR score & item score < 0.85?
                                                          ├── Yes ──► Flag in Review Queue
                                                          └── No  ──► Status: PROCESSED
                                                                              │
                                                                              ▼
                                                                 [Persistence Layer]
                                                      • Supabase PostgreSQL (or In-Memory)
                                                      • Receipts, Line Items, Hashes
```

---

## 2. Zero-Dependency Local Development Mode

The backend includes a **fully functional In-Memory Store and Mock Pipeline Fallback**. This enables development, peer reviews, CI/CD testing, and CLI validation immediately without needing external credentials or database instances.

* **In-Memory Store:** Mirrors the entire relational schema (`receipts`, `line_items`, `receipt_hashes`, `review_queue`, `categories`).
* **Seeded Categories:** 6 baseline categories matching `docs/specifications/05_ERD.md` are pre-seeded at boot.
* **Fallback Hasher:** In-memory pHash and SHA-256 indexing with $O(N)$ fast hamming distance checks.
* **Dual Mode Detection:** If `GOOGLE_APPLICATION_CREDENTIALS` or `SUPABASE_URL` are omitted, the backend logs fallback mode and remains 100% operational.

---

## 3. Production External Services Setup Guide

When transitioning from local development mode to full cloud deployment, follow the steps below to configure Google Cloud Vision, Supabase PostgreSQL, and local OCR engines.

### 3.1 Google Cloud Vision API (Primary Printed OCR)

Google Cloud Vision provides high-accuracy Document Text Detection for printed and thermal receipts.

1. **Create a Google Cloud Project:**
   - Navigate to [Google Cloud Console](https://console.cloud.google.com/).
   - Create a project named `receiptledger-prod`.
2. **Enable the Cloud Vision API:**
   - In the API Library, search for **Cloud Vision API** and click **Enable**.
3. **Create a Service Account:**
   - Go to **IAM & Admin** $\rightarrow$ **Service Accounts** $\rightarrow$ **Create Service Account**.
   - Assign name `vision-ocr-worker`.
   - Grant role: `Cloud Vision User` (or `Viewer`).
4. **Generate JSON Key:**
   - Click on the service account $\rightarrow$ **Keys** $\rightarrow$ **Add Key** $\rightarrow$ **Create new key (JSON)**.
   - Download the key file and save it securely in `backend/credentials/google_vision_key.json`.
5. **Configure `.env`:**
   ```env
   GOOGLE_APPLICATION_CREDENTIALS=credentials/google_vision_key.json
   VISION_API_MONTHLY_QUOTA=950
   ```
   > **Quota Safety:** Google provides 1,000 free requests per month. The backend automatically tracks monthly calls and fails over to Tesseract once 950 calls are reached to prevent unexpected billing.

---

### 3.2 Supabase PostgreSQL Database Setup

1. **Create a Supabase Project:**
   - Sign up at [supabase.com](https://supabase.com) and create an organization/project `receiptledger`.
   - Choose your nearest AWS region (e.g., `ap-south-1` Mumbai / Karachi proximity).
2. **Execute Database Migrations:**
   - Open the **SQL Editor** in the Supabase Dashboard.
   - Open and copy the contents of `backend/app/core/migrations.sql`.
   - Click **Run**. This idempotently generates:
     - `uuid-ossp` and `pg_trgm` extensions
     - `categories` table (with 6 Pakistani expense categories pre-seeded)
     - `users` table
     - `receipts` table with constraints
     - `line_items` table with foreign keys and cascading delete
     - `receipt_hashes` table with btree indices on `phash_64` and `text_fingerprint_sha256`
     - `review_queue` table
     - `v_monthly_category_spend` materialized analytical view
3. **Retrieve API Keys:**
   - Navigate to **Project Settings** $\rightarrow$ **API**.
   - Copy **Project URL**, **anon public key**, and **service_role secret key**.
4. **Configure `.env`:**
   ```env
   SUPABASE_URL=https://<your-project-ref>.supabase.co
   SUPABASE_ANON_KEY=eyJhbGciOi...
   SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOi...
   ```

---

### 3.3 Tesseract OCR 5 Installation (Local Fallback)

Tesseract acts as the zero-cost local OCR engine for printed and offline processing.

#### On Windows:
1. Download the Tesseract 5 installer from [UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki).
2. Run the installer and choose `C:\Program Files\Tesseract-OCR`.
3. Add `C:\Program Files\Tesseract-OCR` to your Windows System `PATH` environment variable.
4. (Optional) For Urdu support, download `urd.traineddata` from [tessdata](https://github.com/tesseract-ocr/tessdata) and place in `C:\Program Files\Tesseract-OCR\tessdata\`.
5. Verify installation in PowerShell:
   ```powershell
   tesseract --version
   ```

#### On Linux / Ubuntu:
```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-urd libtesseract-dev
```

#### On macOS:
```bash
brew install tesseract tesseract-lang
```

---

### 3.4 EasyOCR & PyTorch Setup (Handwritten OCR Fallback)

EasyOCR provides deep learning OCR for complex handwriting and cursive Urdu/Arabic characters.

1. **Install PyTorch:**
   - For CPU-only (recommended for development):
     ```bash
     pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
     ```
   - For NVIDIA GPU (CUDA acceleration):
     ```bash
     pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
     ```
2. **Install EasyOCR:**
   ```bash
   pip install easyocr
   ```
   > **Lazy Loading:** EasyOCR models (~120 MB weights) are lazily loaded into memory only when a handwritten receipt is ingested, keeping startup time under 1 second.

---

## 4. Running the CLI Test Suite

The test suite in `app/cli_test.py` validates all services and API routes end-to-end without requiring a running HTTP server or database.

### Running the Test Suite
From the `backend/` directory:
```powershell
.\.venv\Scripts\python.exe -m app.cli_test
```

### What Is Tested (32 Test Cases):
1. **Config:** `.env` loading and feature flag resolution
2. **Normalizer:** Taxonomy loading, English/Urdu fuzzy matching, price/quantity regex extractors
3. **Deduplication:** pHash computation, Hamming distance, SHA-256 metadata fingerprinting
4. **Store:** In-memory receipt CRUD, review queue flagging, monthly spend aggregation
5. **Preprocessor:** OpenCV blur score calculation, synthetic receipt transformation
6. **OCR Router:** Spatial line reassembly, Tesseract status probe
7. **API Integration (`TestClient`):**
   - `GET /api/v1/health`
   - `POST /api/v1/receipts/upload` (valid receipt ingestion)
   - `POST /api/v1/receipts/upload` (duplicate rejection with HTTP 409)
   - `POST /api/v1/receipts/upload` (empty file `422` & invalid mime `415`)
   - `GET /api/v1/analytics/monthly` & `/trends`
   - `GET /api/v1/review-queue` & `PATCH` item resolution
8. **Sample Receipts Dataset:**
   - Classification and upload of authentic printed thermal receipt
   - Classification and upload of authentic handwritten grocery slip

---

## 5. Sample Receipt Dataset Reference

Sample test images are provided in `data/sample_receipts/`:

| File | Type | Key Features | Test Validation |
|:---|:---:|:---|:---|
| `data/sample_receipts/printed_receipt_sample.jpg` | Thermal Supermarket Receipt | Al-Madina Super Market, Atta 5kg, Rice 2kg, Oil 1L, Milk 1L, Total 2610.00 | Classified as `PRINTED`, blur score 2170.8, routes to Vision/Tesseract |
| `data/sample_receipts/handwritten_receipt_sample.jpg` | Traditional Grocery Parchi | Madina Karyana Store, Atta 10kg, Chawal 2kg, Cheeni 3kg, Ghee 1kg, Total 3030 | Classified as `HANDWRITTEN`, blur score 2517.0, routes to EasyOCR |

---

## 6. API Endpoint Reference & cURL Examples

Once the server is running (`uvicorn app.main:app --port 8000`):

### 6.1 Health Check
```bash
curl -X GET http://localhost:8000/api/v1/health
```
**Response:**
```json
{
  "status": "ok",
  "version": "1.0.0",
  "environment": "development",
  "engines": {
    "cloud_vision": "disabled (no credentials)",
    "tesseract": "not_installed",
    "easyocr": "not_installed",
    "database": "in_memory (dev mode)"
  }
}
```

### 6.2 Upload Receipt Image
```bash
curl -X POST http://localhost:8000/api/v1/receipts/upload \
  -F "file=@../data/sample_receipts/printed_receipt_sample.jpg" \
  -F "device_timestamp=2026-10-09T18:43:00Z" \
  -F "capture_mode=single"
```

### 6.3 Fetch Monthly Spending Summary
```bash
curl -X GET "http://localhost:8000/api/v1/analytics/monthly?year=2026&month=10"
```
**Response:**
```json
{
  "period": "2026-10",
  "total_spend": 2610.0,
  "delta_previous_month": null,
  "receipt_count": 1,
  "category_breakdown": {
    "Groceries & Food": 2610.0
  }
}
```

### 6.4 Review Queue Human-in-the-Loop Resolution
```bash
# List unresolved items
curl -X GET http://localhost:8000/api/v1/review-queue

# Resolve an item
curl -X PATCH http://localhost:8000/api/v1/review-queue/<QUEUE_ID> \
  -H "Content-Type: application/json" \
  -d '{
    "action": "ACCEPTED",
    "confirmed_name": "Wheat Flour (Atta)",
    "confirmed_quantity": 5.0,
    "confirmed_unit": "kg",
    "confirmed_unit_price": 700.0,
    "confirmed_total_price": 700.0
  }'
```

---

## 7. Troubleshooting & Common Issues

| Symptom | Cause | Solution |
|:---|:---|:---|
| `HTTP 415 Unsupported Media Type` | Uploaded file is not JPEG, PNG, or WEBP | Ensure `Content-Type: image/jpeg` or `image/png` |
| `HTTP 409 Conflict` | Visual or textual duplicate detected | Expected behavior. Receipt already exists in ledger. Use different receipt or clean in-memory store. |
| `Tesseract not found on PATH` | Tesseract binary not installed | Install Tesseract 5 via UB-Mannheim installer or apt, or let system use in-memory fallback. |
| `UnicodeEncodeError on Windows CLI` | Windows console codepage 1252 | Handled automatically in `cli_test.py` via UTF-8 wrapped stdout with replacement error handling. |
| `Cloud Vision 403 / 401` | Expired or missing GCP service key | Verify `GOOGLE_APPLICATION_CREDENTIALS` points to a valid JSON file with Cloud Vision permissions. |

---

## 8. "Is Me Being on Google AI Pro Going to Help?" (2026 Analysis)

A common point of confusion is how **Google AI Pro (Google One AI Premium / Gemini Advanced)** interacts with developer APIs. Here is the exact breakdown for 2026:

### 8.1 Consumer Subscription vs. Developer APIs
* **What Google AI Pro Gives You:**
  - Access to Gemini Advanced on the web (`gemini.google.com`) and mobile app.
  - 2 TB Google Drive / Photos / Gmail storage.
  - Gemini in Google Docs, Gmail, and Google Slides.
  - **Important:** It **does NOT** provide automatic API credits for **Google Cloud Platform (GCP Cloud Vision API)** or **Google Cloud Vertex AI**. They use completely separate billing accounts.
* **Is It Going to Help with ReceiptLedger?**
  - **Indirectly, yes:** You can use your Google AI Pro subscription to upload messy receipts directly into the Gemini web UI for rapid prompt engineering, manual benchmark comparisons, or sanity checking difficult handwritten Urdu parchi receipts.
  - **Directly for the backend:** You do **not** need to spend a single penny, because Google provides developer tiers that are **100% free** regardless of whether you have Google AI Pro.

### 8.2 The 100% Free Developer Alternative: Google AI Studio
Google provides **Google AI Studio** (`aistudio.google.com`) which is **completely free for developers**:
* **Gemini 1.5 Flash / Gemini 2.0 Flash Developer API:**
  - **Rate Limit:** 15 Requests Per Minute (RPM), **1,500 Requests Per Day (RPD)**, and 1,000,000 Tokens Per Minute.
  - **Cost:** **$0.00 (Completely Free, No Credit Card Required)**.
  - **Multimodal Receipt OCR:** You can pass receipt images directly to Gemini Flash and prompt it to extract structured JSON with Pakistani grocery entities, serving as an optional zero-cost cloud OCR engine.
* **Google Cloud Vision Free Tier:**
  - **Quota:** **1,000 Document Text Detection requests every month for free forever**.
  - **GCP New Account Credit:** If you open a new GCP billing account with your Google account, you get **$300 free trial credit for 90 days**.

---

## 9. 2026 Free-Tier Master Stack & Setup Checklist

You can run the entire ReceiptLedger stack in production **at zero cost ($0.00/month)**:

| Layer | Service / Technology | Free Allowance | Configuration Key in `.env` |
|:---|:---|:---|:---|
| **Primary Cloud OCR** | Google Cloud Vision API | 1,000 calls / month free forever | `GOOGLE_APPLICATION_CREDENTIALS` |
| **Multimodal Vision Fallback** | Google AI Studio (Gemini Flash) | 1,500 calls / day free forever | Optional `GEMINI_API_KEY` |
| **Local Printed OCR** | Tesseract OCR 5 | Unlimited (runs on your CPU) | System `PATH` |
| **Local Handwritten OCR** | EasyOCR + PyTorch | Unlimited (runs on your CPU/GPU) | Python package `easyocr` |
| **Database & Storage** | Supabase PostgreSQL | 500 MB database + 1 GB storage free | `SUPABASE_URL`, `SUPABASE_ANON_KEY` |
| **Dev Persist Fallback** | In-Memory Store | Unlimited (zero dependencies) | Default when Supabase keys omitted |
| **Mobile Client** | Flutter 3.x Client | Unlimited (Windows, Web, Android) | `API_BASE_URL` |

### Step-by-Step Free Setup Checklist:
1. **Google Cloud Vision (0 PKR / $0):**
   - Go to [console.cloud.google.com](https://console.cloud.google.com).
   - Create project `receiptledger`.
   - Enable **Cloud Vision API**.
   - Create a service account with `Cloud Vision User` role and download `credentials/google_vision_key.json`.
   - Keep `VISION_API_MONTHLY_QUOTA=950` in `.env` so you never exceed the 1,000 free request limit.
2. **Supabase PostgreSQL (0 PKR / $0):**
   - Go to [supabase.com](https://supabase.com) and create a free project.
   - Go to **SQL Editor**, paste `backend/app/core/migrations.sql`, and click **Run**.
   - Copy Project URL and `anon` public key to `backend/.env`.
3. **Local OCR (0 PKR / $0):**
   - Windows: Install Tesseract 5 from UB-Mannheim into `C:\Program Files\Tesseract-OCR` and add to PATH.
   - Run `python -m app.cli_test` to verify all 32 tests pass.

---

## 10. Flutter Mobile Frontend Testing Guide

A cross-platform Flutter frontend is located in `mobile/`. It supports live receipt capture, gallery picking, instant uploading, result inspection, recent ledger viewing, and review queue verification.

### 10.1 Running the Mobile App
From the `mobile/` directory:

* **On Windows Desktop (Fastest for testing):**
  ```powershell
  flutter run -d windows
  ```
* **On Web Browser (Chrome):**
  ```powershell
  flutter run -d chrome
  ```
* **On Android Emulator:**
  ```powershell
  flutter run -d emulator
  ```
* **On Physical Android/iOS Device:**
  ```powershell
  flutter run -d <device-id>
  ```

### 10.2 Connecting to Backend
In the app's **Settings tab**:
* If running on **Windows Desktop** or **Chrome Web**: Use preset `http://127.0.0.1:8000`.
* If running on **Android Emulator**: Use preset `http://10.0.2.2:8000`.
* If running on a **Physical Phone via Wi-Fi**: Enter your workstation's LAN IP, e.g. `http://192.168.1.50:8000`.
* Tap **Save & Test Connection** to verify live communication with the FastAPI backend.

### 10.3 Testing Features in the App:
1. **Capture Tab:** Pick any receipt photo or select one from `data/sample_receipts/`. Tap **Upload & Process Receipt**. Inspect the extracted merchant name, date, total amount, confidence badge, and itemized table.
2. **Ledger Tab:** View all processed receipts. Tap any card to expand and review its itemized lines.
3. **Review Queue Tab:** Inspect items flagged with confidence $< 0.85$. Tap **Edit / Correct** to adjust names or prices and submit human-in-the-loop resolutions.

---

## 11. Challenging Test Receipts Dataset

In addition to standard receipts, challenging test images have been included in `data/sample_receipts/` to stress-test preprocessing and classification:

| File | Challenge Type | Real-World Scenario | Preprocessing / OCR Behavior |
|:---|:---|:---|:---|
| `printed_receipt_challenging.jpg` | **Crumpled & Faded Thermal Paper** | Paper with fold creases, torn bottom edge, smudged thermal print on right margin (*Imtiaz Super Market, Clifton*). | OpenCV CLAHE enhances faded print; deskew corrects tilt; classified as `PRINTED`. |
| `handwritten_receipt_challenging.jpg` | **Messy & Rushed Scrap Slip** | Torn spiral notebook paper, skewed angle, rushed cursive Urdu/English handwriting (*Bismillah General Store*). | Blur variance check verifies sharpness; height CV ($1.75 > 1.25$) routes to `HANDWRITTEN` (EasyOCR). |
| `printed_receipt_sample.jpg` | **Standard Thermal Receipt** | Flat, crisp thermal print from supermarket with PKR amounts (*Al-Madina Super Market*). | Standard baseline; routes to Vision / Tesseract. |
| `handwritten_receipt_sample.jpg` | **Standard Lined Parchi** | Ruled notepad paper with neat Urdu/English handwriting (*Madina Karyana Store*). | Lined baseline; routes to EasyOCR. |

