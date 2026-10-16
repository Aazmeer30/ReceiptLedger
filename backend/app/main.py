"""
ReceiptLedger – FastAPI Application Entrypoint
================================================
Configures:
  • Application metadata (title, version, description)
  • CORS middleware
  • API routers mounted under /api/v1
  • Startup event (log configuration summary)
  • Global exception handlers

Run with:
    uvicorn app.main:app --reload --port 8000 --host 0.0.0.0

References:
  docs/09_DEVELOPMENT_PLAN.md § 2 (Ingestion & Gateway Tier)
  docs/09_DEVELOPMENT_PLAN.md § 4 Day 1 (FastAPI skeleton)
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import analytics, auth, dashboard, health, receipts, review_queue, system
from app.core.config import settings
from app.services import store

# ── Logging Configuration ─────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.DEBUG if settings.is_development else logging.INFO,
    format="%(asctime)s  [%(levelname)-8s]  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("receiptledger")


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle manager.
    Runs startup tasks before the server starts accepting requests.
    """
    logger.info("=" * 60)
    logger.info("ReceiptLedger Backend  v1.0.0 (Unified Monorepo Gateway)")
    logger.info("Environment  : %s", settings.environment)
    logger.info("Supabase     : %s", "enabled" if settings.supabase_enabled else "disabled (in-memory store)")
    logger.info("Cloud Vision : %s", "enabled" if settings.cloud_vision_enabled else "disabled (Tesseract fallback)")
    logger.info("Listening on : http://%s:%d", settings.host, settings.port)
    logger.info("Swagger UI   : http://%s:%d/docs", settings.host, settings.port)
    logger.info("=" * 60)

    # Pre-warm: Set Google credentials env var if configured
    if settings.google_application_credentials:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = settings.google_application_credentials
        logger.info("Google credentials path set.")

    # In development mode, auto-seed realistic sample data if store is empty
    if settings.is_development and settings.seed_demo_data_on_startup:
        existing = store.list_receipts()
        if len(existing) == 0:
            seeded = store.seed_demo_data()
            logger.info("Auto-seeded demo data for dashboard: %s receipts, %s items, %s review items",
                        seeded["receipts"], seeded["line_items"], seeded["review_items"])

    yield  # Server is running

    logger.info("ReceiptLedger backend shutting down.")


# ── FastAPI Application ───────────────────────────────────────────────────────

app = FastAPI(
    title="ReceiptLedger API",
    description=(
        "Backend REST API for automated receipt digitisation, OCR processing, "
        "NLP normalization, and spending analytics.  "
        "Part of the ReceiptLedger project — SPM-458, University of Karachi."
    ),
    version="1.0.0",
    contact={
        "name": "Muhammad Asad Khan (Lead Architect)",
        "url": "https://github.com/Asad101001/ReceiptLedger",
    },
    license_info={"name": "MIT"},
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Configured for Monorepo architecture: allows mobile app & web dashboard (Vite / React)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# ── Global Exception Handler ──────────────────────────────────────────────────

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception on %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected internal server error occurred."},
    )

# ── API Routers ───────────────────────────────────────────────────────────────

API_PREFIX = "/api/v1"

app.include_router(auth.router,          prefix=API_PREFIX)
app.include_router(health.router,        prefix=API_PREFIX)
app.include_router(receipts.router,      prefix=API_PREFIX)
app.include_router(analytics.router,     prefix=API_PREFIX)
app.include_router(review_queue.router,  prefix=API_PREFIX)
app.include_router(dashboard.router,     prefix=API_PREFIX)
app.include_router(system.router,        prefix=API_PREFIX)


# ── Root redirect ─────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {
        "service": "ReceiptLedger Unified Monorepo API Gateway",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/v1/health",
        "dashboard_overview": "/api/v1/dashboard/overview",
        "review_queue": "/api/v1/review-queue",
    }

