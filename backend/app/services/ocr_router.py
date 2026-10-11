"""
ReceiptLedger – OCR Decision Router & Spatial Line Reassembly
==============================================================
Responsibilities:
  1. Classify receipt type (PRINTED / HANDWRITTEN) using edge density heuristic.
  2. Route to the correct OCR engine with quota-aware fallback logic.
  3. Reassemble flat OCR token lists into logical horizontal text lines.

Routing priority:
  PRINTED  → Cloud Vision API → (quota fallback) Tesseract 5
  HANDWRITTEN → EasyOCR + Tesseract digit voting

Concurrency control:
  An asyncio.Semaphore limits simultaneous heavy OCR tasks to prevent
  memory saturation from concurrent EasyOCR inference.

References:
  docs/09_DEVELOPMENT_PLAN.md § 3.2, 3.3
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Tuple

import numpy as np

from app.core.config import settings
from app.core.models import OCRToken, ReceiptType

logger = logging.getLogger(__name__)

# Semaphore: max concurrent heavy OCR tasks (EasyOCR is ~500 MB RAM per call)
_ocr_semaphore = asyncio.Semaphore(settings.max_concurrent_ocr)


# ── Receipt Type Classifier ───────────────────────────────────────────────────

def classify_receipt_type(image: np.ndarray) -> ReceiptType:
    """
    Heuristic classifier: distinguishes structured machine-printed receipts
    from informal handwritten slips using edge density and connected component
    analysis. Now calibrated for CLAHE-enhanced grayscale (not binarized) images.

    Printed receipts: strong horizontal edge regularity, high uniform glyph density.
    Handwritten slips: irregular stroke widths, lower edge periodicity.
    """
    import cv2

    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    # ── Feature 1: Edge density via Canny ─────────────────────────────────────
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blurred, 50, 150)
    edge_density = np.count_nonzero(edges) / max(edges.size, 1)

    # ── Feature 2: Glyph height variance & aspect ratio (connected components) ──
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    _, _, stats, _ = cv2.connectedComponentsWithStats(thresh)
    # Filter out table dividers, border frames, and speckle noise to isolate text glyphs
    valid_stats = [
        s for s in stats[1:]
        if 8 <= s[cv2.CC_STAT_HEIGHT] <= 120
        and 4 <= s[cv2.CC_STAT_WIDTH] <= 200
        and s[cv2.CC_STAT_AREA] >= 15
    ]

    if not valid_stats:
        return ReceiptType.PRINTED

    heights = [s[cv2.CC_STAT_HEIGHT] for s in valid_stats]
    widths  = [s[cv2.CC_STAT_WIDTH]  for s in valid_stats]
    mean_h = float(np.mean(heights)) + 1e-5
    std_h  = float(np.std(heights))
    cv_h   = std_h / mean_h

    # Aspect ratio: printed chars are tall and narrow (aspect ~0.55-0.70);
    # handwritten cursive words sprawl horizontally (aspect > 0.95)
    mean_aspect = float(np.mean([w / (h + 1e-5) for w, h in zip(widths, heights)]))

    # ── Decision rule ──────────────────────────────────────────────────────────
    if mean_aspect > 0.92 or cv_h > 0.55:
        return ReceiptType.HANDWRITTEN

    return ReceiptType.PRINTED


# ── OCR Routing & Extraction ──────────────────────────────────────────────────

async def route_and_extract(
    image: np.ndarray,
    image_bytes: bytes,
    receipt_type: ReceiptType,
) -> Tuple[List[OCRToken], str]:
    """
    Route to the appropriate OCR engine and extract tokens.

    Returns:
        (tokens, engine_used): The extracted OCR tokens and a string
        identifying which engine was used (for logging/debugging).
    """
    async with _ocr_semaphore:
        if receipt_type == ReceiptType.PRINTED:
            return await _extract_printed(image_bytes)
        else:
            return await _extract_handwritten(image)


async def _extract_printed(image_bytes: bytes) -> Tuple[List[OCRToken], str]:
    """
    Printed path: Cloud Vision → Tesseract fallback.
    """
    # Try Cloud Vision first
    if settings.cloud_vision_enabled:
        try:
            from app.services.cloud_vision_client import (
                CloudVisionQuotaExceededError,
                extract_tokens as cv_extract,
                is_available as cv_available,
            )
            if cv_available():
                logger.info("Using Google Cloud Vision for printed receipt.")
                loop = asyncio.get_event_loop()
                tokens = await loop.run_in_executor(None, cv_extract, image_bytes)
                return tokens, "cloud_vision"
        except CloudVisionQuotaExceededError:
            logger.warning(
                "Cloud Vision quota reached. Falling back to Tesseract for this request."
            )
        except Exception as exc:
            logger.warning("Cloud Vision unavailable (%s). Falling back to Tesseract.", exc)

    # Fallback: Tesseract (printed path uses clean English)
    return await _run_tesseract(image_bytes, lang="eng")


async def _extract_handwritten(image: np.ndarray) -> Tuple[List[OCRToken], str]:
    """
    Handwritten path: EasyOCR with Tesseract digit voting.
    Falls back to Tesseract (eng first, then eng+urd if empty).
    """
    try:
        from app.services.easyocr_client import (
            extract_tokens as easy_extract,
            is_available as easy_available,
        )
        if easy_available():
            logger.info("Using EasyOCR for handwritten receipt.")
            loop = asyncio.get_event_loop()
            tokens = await loop.run_in_executor(None, easy_extract, image)
            if tokens:
                return tokens, "easyocr"
    except Exception as exc:
        logger.warning("EasyOCR failed (%s). Falling back to Tesseract.", exc)

    # Fallback: Tesseract. Pakistani karyana slips write product names in Roman Urdu/English (Atta, Chawal, Daal).
    # 'eng' OCR prevents Urdu LSTM ligature hallucination on Roman text.
    tokens, eng = await _run_tesseract(None, image=image, lang="eng")
    if len(tokens) >= 3:
        return tokens, eng

    # If 'eng' yielded very few tokens, try eng+urd
    from app.services.tesseract_client import _get_ocr_lang
    fallback_lang = _get_ocr_lang()
    if fallback_lang != "eng":
        return await _run_tesseract(None, image=image, lang=fallback_lang)
    return tokens, eng


async def _run_tesseract(
    image_bytes: bytes | None,
    image: np.ndarray | None = None,
    lang: str | None = None,
) -> Tuple[List[OCRToken], str]:
    """Run Tesseract 5 extraction (used as fallback for both paths)."""
    import functools
    import numpy as _np

    from app.services.tesseract_client import (
        extract_tokens as tess_extract,
        is_available as tess_available,
    )

    if not tess_available():
        logger.error("Tesseract is not installed or not on PATH.")
        return [], "none"

    if image is None:
        np_arr = _np.frombuffer(image_bytes, dtype=_np.uint8)
        import cv2
        image = cv2.imdecode(np_arr, cv2.IMREAD_GRAYSCALE)

    loop = asyncio.get_event_loop()
    tokens = await loop.run_in_executor(
        None, functools.partial(tess_extract, image, lang=lang)
    )
    logger.info("Tesseract extracted %d tokens (lang=%s).", len(tokens), lang)
    return tokens, "tesseract"


# ── Spatial Line Reassembly ───────────────────────────────────────────────────

def _estimate_text_slant(tokens: List[OCRToken]) -> float:
    """
    Estimate dominant text baseline angle (in degrees).
    Prioritises same-line token pairs (via line_id from Tesseract) to eliminate
    cross-line slope noise, with a fallback to proximate horizontal pairs.
    """
    if len(tokens) < 4:
        return 0.0

    slopes = []
    # 1. Prefer tokens with identical line_id (from Tesseract output)
    by_line: dict = {}
    for t in tokens:
        lid = getattr(t, "line_id", None)
        if lid is not None:
            by_line.setdefault(lid, []).append(t)

    for lid, line_toks in by_line.items():
        if len(line_toks) >= 2:
            s_line = sorted(line_toks, key=lambda x: x.bounding_box.x_min)
            for k in range(len(s_line) - 1):
                t1, t2 = s_line[k], s_line[k + 1]
                dx = t2.bounding_box.x_center - t1.bounding_box.x_center
                dy = t2.bounding_box.y_center - t1.bounding_box.y_center
                if dx > 25 and abs(dy) < 40:
                    deg = float(np.degrees(np.arctan2(dy, dx)))
                    if abs(deg) < 15.0:
                        slopes.append(deg)

    if len(slopes) >= 4:
        return float(np.median(slopes))

    # 2. Fallback: proximate horizontal pairs across receipt
    by_x = sorted(tokens, key=lambda t: t.bounding_box.x_min)
    n = len(by_x)
    for i in range(n):
        for j in range(i + 1, min(i + 8, n)):
            t1, t2 = by_x[i], by_x[j]
            dx = t2.bounding_box.x_center - t1.bounding_box.x_center
            dy = t2.bounding_box.y_center - t1.bounding_box.y_center
            if 50 < dx < 350 and abs(dy) < 25:
                deg = float(np.degrees(np.arctan2(dy, dx)))
                if abs(deg) < 15.0:
                    slopes.append(deg)

    if slopes:
        return float(np.median(slopes))
    return 0.0


def reassemble_lines(
    tokens: List[OCRToken],
    y_tolerance: int = 15,
) -> List[List[OCRToken]]:
    """
    Group flat OCR token list into logical horizontal text lines.
    Accounts for camera tilt/slant by projecting token y-coordinates along the
    dominant text baseline angle. Ensures item names on the left and prices on
    the right stay on the same logical line without being broken across blocks.
    """
    if not tokens:
        return []

    # Clean out single-character non-alphanumeric noise speckles with low confidence
    valid_tokens = [
        t for t in tokens
        if len(t.text.strip()) > 1 or t.text.strip().isalnum() or t.confidence >= 0.35
    ]
    if not valid_tokens:
        valid_tokens = tokens

    # Estimate slant angle
    deg = _estimate_text_slant(valid_tokens)
    rad = np.radians(deg)
    tan_theta = np.tan(rad)

    # Assign projected y to each token
    for t in valid_tokens:
        proj_y = t.bounding_box.y_center - (t.bounding_box.x_center * tan_theta)
        setattr(t, "_proj_y", proj_y)

    sorted_tokens = sorted(valid_tokens, key=lambda t: getattr(t, "_proj_y"))
    lines: List[List[OCRToken]] = []

    for token in sorted_tokens:
        placed = False
        t_y = getattr(token, "_proj_y")
        t_h = token.bounding_box.y_max - token.bounding_box.y_min

        for line in lines:
            line_y = sum(getattr(x, "_proj_y") for x in line) / len(line)
            line_h = sum(x.bounding_box.y_max - x.bounding_box.y_min for x in line) / len(line)
            # Generous tolerance to keep multi-column items & prices unified on the same row
            max_diff = max(16, max(t_h, line_h) * 0.70)

            if abs(t_y - line_y) <= max_diff:
                line.append(token)
                placed = True
                break

        if not placed:
            lines.append([token])

    # Sort tokens in each line left-to-right
    for line in lines:
        line.sort(key=lambda t: t.bounding_box.x_min)

    # Sort lines top-to-bottom
    lines.sort(key=lambda l: sum(getattr(t, "_proj_y") for t in l) / len(l))
    logger.debug(
        "Reassembled %d tokens into %d lines (slant=%.2f deg).",
        len(valid_tokens), len(lines), deg,
    )
    return lines
