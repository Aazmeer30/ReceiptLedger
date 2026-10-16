"""
ReceiptLedger – Receipt Upload Endpoint
POST /api/v1/receipts/upload

Accepts a multipart/form-data upload containing the receipt image plus optional
metadata (device_timestamp, capture_mode).  Runs the full ingestion pipeline
and returns the structured UploadReceiptResponse.

HTTP Status codes:
  200  Successfully processed (PROCESSED or PENDING_REVIEW)
  409  Duplicate receipt detected
  413  File too large
  422  Image could not be processed (blur, decode error, etc.)
  500  Internal pipeline failure
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

from app.core.auth import UserSession, get_current_user
from app.core.config import settings
from app.core.models import ReceiptStatus, UploadReceiptResponse
from app.services.ingestion import ingest_receipt

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/receipts/upload",
    response_model=UploadReceiptResponse,
    summary="Upload and process a receipt image",
    tags=["Receipts"],
    responses={
        409: {"description": "Duplicate receipt – already exists in the ledger."},
        413: {"description": "File exceeds maximum allowed size (10 MB)."},
        422: {"description": "Image cannot be processed (blurry, corrupt, or unsupported format)."},
    },
)
async def upload_receipt(
    file: UploadFile = File(..., description="JPEG or PNG receipt image"),
    device_timestamp: Optional[str] = Form(
        None,
        description="ISO-8601 timestamp from the capturing device (e.g. 2026-10-05T14:30:00Z)",
    ),
    capture_mode: str = Form(
        "single",
        description="'single' for one receipt, 'batch' for multi-receipt session",
    ),
    ocr_engine: str = Form(
        "auto",
        description="'auto' (prefers Gemini if configured, with local fallback), 'gemini', or 'local'",
    ),
    current_user: UserSession = Depends(get_current_user),
) -> UploadReceiptResponse:
    """
    Multipart receipt image upload endpoint.

    Orchestrates the full pipeline:
    1. Validate file type and size
    2. OpenCV preprocessing (deskew, contrast)
    3. OCR extraction (Cloud Vision or EasyOCR/Tesseract)
    4. NLP normalization and fuzzy matching
    5. Deduplication check (pHash + text fingerprint)
    6. Database insertion
    7. Review queue flagging for low-confidence items
    """
    # ── Read and size-check file ──────────────────────────────────────────────
    image_bytes = await file.read()
    if len(image_bytes) == 0:
        raise HTTPException(
            status_code=422,
            detail="Uploaded file is empty.",
        )

    if len(image_bytes) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size {len(image_bytes)} bytes exceeds limit of {settings.max_upload_bytes} bytes.",
        )

    # ── File type validation (Magic bytes, extension, or Content-Type) ────────
    raw_content_type = (file.content_type or "").lower()
    filename_lower = (file.filename or "").lower()

    is_jpeg = image_bytes.startswith(b"\xff\xd8\xff")
    is_png = image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    is_webp = len(image_bytes) > 12 and image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP"
    has_valid_ext = filename_lower.endswith((".jpg", ".jpeg", ".png", ".webp"))
    has_valid_mime = raw_content_type in ("image/jpeg", "image/jpg", "image/png", "image/webp")

    if not (is_jpeg or is_png or is_webp or has_valid_ext or has_valid_mime):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {raw_content_type or 'unknown'}. Accepted: JPEG, PNG, WEBP.",
        )

    # ── Run ingestion pipeline ────────────────────────────────────────────────
    try:
        result = await ingest_receipt(
            image_bytes=image_bytes,
            device_timestamp=device_timestamp,
            capture_mode=capture_mode,
            user_id=current_user.user_id,
            ocr_engine=ocr_engine,
        )
    except ValueError as exc:
        # Image could not be decoded or is too blurry
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error("Ingestion pipeline error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Receipt processing failed. Please try again.",
        )

    # ── Duplicate → 409 ──────────────────────────────────────────────────────
    if result.status == ReceiptStatus.DUPLICATE:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=result.model_dump(mode="json"),
        )

    return result
