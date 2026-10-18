<div align="center">

# ReceiptLedger / Backend Service

**FastAPI Core Engine for Receipt Preprocessing, Dual OCR Routing, and Expense Normalization.**

[![Runtime](https://img.shields.io/badge/Python-3.11%20%7C%203.12-3776AB?style=flat-square&logo=python&logoColor=white)](#)
[![Framework](https://img.shields.io/badge/Framework-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](#)
[![Computer Vision](https://img.shields.io/badge/CV-OpenCV-5C3EE8?style=flat-square&logo=opencv&logoColor=white)](#)
[![Cloud OCR](https://img.shields.io/badge/OCR-Google%20Vision-4285F4?style=flat-square&logo=googlecloud&logoColor=white)](#)
[![Local OCR](https://img.shields.io/badge/OCR-EasyOCR%20%2B%20Tesseract-7C3AED?style=flat-square)](#)
[![Database](https://img.shields.io/badge/Persistence-Supabase%20%2F%20PostgreSQL-3ECF8E?style=flat-square&logo=supabase&logoColor=white)](#)

</div>

---

## Overview

The `backend` service orchestrates receipt image ingestion, perspective correction, text extraction, fuzzy dictionary mapping, duplicate prevention, and transactional persistence.

```
Incoming Image ──► OpenCV Deskew ──► Dual OCR Router ──► Normalizer ──► Deduplication ──► PostgreSQL
```

---

## Directory Structure

```text
backend/
├── Dockerfile             # Container definition with Tesseract & OpenCV libs
├── .dockerignore          # Docker build exclusion rules
├── .env.example           # Environment template (API keys, DB URLs)
├── requirements.txt       # Production dependencies
└── app/
    ├── __init__.py
    ├── main.py            # FastAPI application entrypoint
    ├── api/               # API routers (/upload, /analytics, /review)
    ├── core/              # Config, security, and logging
    └── services/          # OpenCV deskew, OCR engines, normalizer, dedup
```

---

## Local Development Setup

### 1. Python Virtual Environment

```powershell
# Create virtual environment
python -m venv .venv

# Activate on Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env`:
```powershell
cp .env.example .env
```
Populate your Google Cloud service account path and Supabase credentials.

### 3. Launch the Server

```powershell
uvicorn app.main:app --reload --port 8000
```
API Documentation will be live at:
* Swagger UI: `http://localhost:8000/docs`
* ReDoc: `http://localhost:8000/redoc`

### 4. Run Comprehensive CLI Test Suite (32 Tests)

Test the entire pipeline, all OCR paths, dedup engine, in-memory store, API endpoints, and real sample receipts without running a server or database:

```powershell
python -m app.cli_test
```

---

## Operations & Production Setup Guide

For detailed step-by-step instructions on setting up Google Cloud Vision, Supabase PostgreSQL DDL migrations, Tesseract OCR 5, and testing with real sample receipt images, see:

📖 **[Backend Setup & Operations Guide](../docs/guides/BACKEND_SETUP_AND_OPERATIONS_GUIDE.md)**

---

## Containerized Execution (Docker)

```bash
docker build -t receiptledger-backend .
docker run -p 8000:8000 --env-file .env receiptledger-backend
```

---

## Key Interfaces

| Endpoint | Method | Description |
|:---|:---:|:---|
| `/api/v1/health` | `GET` | Health check and engine status |
| `/api/v1/auth/login` | `POST` | Authenticate user credentials and issue JWT session token |
| `/api/v1/auth/register` | `POST` | Register a new user account |
| `/api/v1/auth/me` | `GET` | Inspect active user session profile |
| `/api/v1/receipts/upload` | `POST` | Multipart receipt photo ingestion, duplicate check, and parsing |
| `/api/v1/analytics/monthly` | `GET` | Aggregated monthly spend and category rollups |
| `/api/v1/analytics/trends` | `GET` | Multi-month spending velocity trends |
| `/api/v1/analytics/receipts` | `GET` | Paginated, searchable historical receipt ledger |
| `/api/v1/review-queue` | `GET` | Items with confidence $< 0.85$ requiring confirmation |
| `/api/v1/review-queue/{id}` | `PATCH` | Human-in-the-loop verification resolution |
| `/api/v1/system/runs` | `GET` | List observability logs and historical evaluation runs |
| `/api/v1/system/runs/{id}` | `GET` | Inspect full details of a specific benchmark/eval run |

---

## Observability & Evaluation Runs

All evaluation test runs and benchmark outputs are automatically logged into `backend/logs/runs/` with timestamped descriptors:
`YYYYMMDD_HHMMSS_<descriptor>.json`

### Evaluation Commands

1. **Test all 33 images with Gemini Vision**:
   ```powershell
   python test_all_images_gemini.py
   ```
   Evaluates all sample receipts and real web/SROIE receipts, calculates extraction accuracy, and saves a timestamped run log in `logs/runs/`.

2. **A/B Test Gemini vs Local Tesseract Pipeline**:
   ```powershell
   python test_all_gemini_full.py
   ```


