"""
ReceiptLedger – Google Cloud Vision API Client
================================================
Wraps the google-cloud-vision SDK TEXT_DETECTION call and translates the raw
AnnotateImageResponse into the unified OCRToken schema used throughout the pipeline.

Quota management:
  - A persistent counter (stored in the `api_call_counts` in-memory dict) tracks the
    number of calls made in the current billing period.
  - At ≥ 950 calls (configurable via settings.vision_api_monthly_quota) the client
    raises CloudVisionQuotaExceededError which the OCR router catches to fall back
    to Tesseract.

References:
  docs/09_DEVELOPMENT_PLAN.md § 3.2 – Google Cloud Vision Client
"""

from __future__ import annotations

import logging
import os
from typing import List

import numpy as np

from app.core.config import settings
from app.core.models import BoundingBox, OCRToken

logger = logging.getLogger(__name__)

# Simple in-memory request counter (resets on server restart; good enough
# for free-tier quota management within a deployment session).
_api_call_count: int = 0
_billing_disabled: bool = False


class CloudVisionQuotaExceededError(Exception):
    """Raised when the configured quota limit is reached."""


def is_available() -> bool:
    """Return True if Cloud Vision credentials are configured and the SDK is importable."""
    if _billing_disabled:
        return False
    cred_path = settings.google_application_credentials
    if not cred_path:
        return False
    # Set the env var expected by the Google SDK
    os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", cred_path)
    try:
        from google.cloud import vision  # noqa: F401
        return True
    except ImportError:
        return False


def get_remaining_quota() -> int:
    """Return the estimated number of Cloud Vision calls remaining this period."""
    return max(0, settings.vision_api_monthly_quota - _api_call_count)


def extract_tokens(image_bytes: bytes) -> List[OCRToken]:
    """
    Submit the image bytes to Cloud Vision TEXT_DETECTION and return normalised
    OCRToken objects.

    Raises:
        CloudVisionQuotaExceededError: When quota threshold is reached.
        RuntimeError: For API-level failures.
    """
    global _api_call_count

    if _api_call_count >= settings.vision_api_monthly_quota:
        raise CloudVisionQuotaExceededError(
            f"Cloud Vision quota sentinel triggered at {_api_call_count} calls."
        )

    try:
        from google.cloud import vision
    except ImportError as exc:
        raise RuntimeError("google-cloud-vision package is not installed.") from exc

    cred_path = settings.google_application_credentials
    if cred_path:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred_path

    client = vision.ImageAnnotatorClient()
    image_obj = vision.Image(content=image_bytes)

    try:
        response = client.text_detection(image=image_obj)
        _api_call_count += 1
    except Exception as exc:
        err_msg = str(exc)
        if "BILLING_DISABLED" in err_msg or "billing to be enabled" in err_msg:
            global _billing_disabled
            _billing_disabled = True
            logger.warning("Google Cloud Vision API disabled: billing is not enabled on this GCP project. Automatically falling back to local OCR / Gemini.")
        else:
            logger.error("Cloud Vision API call failed: %s", exc)
        raise RuntimeError(f"Cloud Vision API error: {exc}") from exc

    if response.error.message:
        raise RuntimeError(f"Cloud Vision error: {response.error.message}")

    annotations = response.text_annotations
    if not annotations:
        logger.warning("Cloud Vision returned no text annotations.")
        return []

    tokens: List[OCRToken] = []

    # Index 0 is the full aggregated text block — skip it.
    for ann in annotations[1:]:
        raw_text = ann.description.strip()
        if not raw_text:
            continue

        # Extract axis-aligned bounding box from the 4-vertex polygon
        vertices = ann.bounding_poly.vertices
        xs = [v.x for v in vertices]
        ys = [v.y for v in vertices]

        # Cloud Vision does not return per-word confidence directly;
        # we assign a high default confidence for detected words.
        tokens.append(
            OCRToken(
                text=raw_text,
                confidence=0.95,  # Cloud Vision is considered high-fidelity for printed text
                bounding_box=BoundingBox(
                    x_min=min(xs), y_min=min(ys),
                    x_max=max(xs), y_max=max(ys),
                ),
            )
        )

    logger.info(
        "Cloud Vision extracted %d tokens. API call count: %d/%d",
        len(tokens),
        _api_call_count,
        settings.vision_api_monthly_quota,
    )
    return tokens
