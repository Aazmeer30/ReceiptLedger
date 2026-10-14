"""
ReceiptLedger – Health Check Endpoint
/api/v1/health  GET
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.core.config import settings
from app.core.models import EngineStatus, HealthResponse

logger = logging.getLogger(__name__)
router = APIRouter()

APP_VERSION = "1.0.0"


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="System health and engine status check",
    tags=["System"],
)
async def health_check() -> HealthResponse:
    """
    Returns the operational status of the backend and all OCR engines.
    Used by CI pipelines, the Docker health-check, and the web dashboard
    status indicator.
    """
    # ── Cloud Vision ──────────────────────────────────────────────────────────
    try:
        from app.services.cloud_vision_client import (
            get_remaining_quota,
            is_available as cv_available,
        )
        cv_status = f"ok (quota_remaining={get_remaining_quota()})" if cv_available() else "disabled (no credentials)"
    except Exception as exc:
        cv_status = f"error: {exc}"

    # ── Tesseract ─────────────────────────────────────────────────────────────
    try:
        from app.services.tesseract_client import is_available as tess_available
        tess_status = "ok" if tess_available() else "not_installed"
    except Exception as exc:
        tess_status = f"error: {exc}"

    # ── EasyOCR ───────────────────────────────────────────────────────────────
    try:
        from app.services.easyocr_client import is_available as easy_available
        easy_status = "ok (lazy-loaded)" if easy_available() else "not_installed"
    except Exception as exc:
        easy_status = f"error: {exc}"

    # ── Gemini (Google AI Studio) ─────────────────────────────────────────────
    try:
        from app.services.gemini_client import is_available as gemini_available
        gemini_status = f"ok (model={settings.gemini_model})" if gemini_available() else "disabled (no API key)"
    except Exception as exc:
        gemini_status = f"error: {exc}"

    # ── Database ──────────────────────────────────────────────────────────────
    db_status = "supabase" if settings.supabase_enabled else "in_memory (dev mode)"

    return HealthResponse(
        status="ok",
        version=APP_VERSION,
        environment=settings.environment,
        engines=EngineStatus(
            cloud_vision=cv_status,
            tesseract=tess_status,
            easyocr=easy_status,
            gemini=gemini_status,
            database=db_status,
        ),
    )
