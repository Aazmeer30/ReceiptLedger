"""
ReceiptLedger - Google Gemini Vision Client
===========================================
Sends a receipt image to Gemini (via Google AI Studio API key) and parses
the structured JSON response into LineItemCreate objects.

This is an ADDITIVE path. The existing Tesseract/EasyOCR/Cloud Vision pipeline
is completely untouched. Use this client for A/B comparison against local OCR.

Routing:
  gemini_enabled (GEMINI_API_KEY set) -> Gemini 2.0 Flash
  Disabled / error                    -> None (caller falls back to local OCR)

References:
  docs/09_DEVELOPMENT_PLAN.md section 3.2 (OCR routing)
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.models import LineItemCreate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Structured extraction prompt
# ---------------------------------------------------------------------------
_RECEIPT_PROMPT = (
    "You are a receipt parsing assistant. Analyse the provided receipt image carefully.\n\n"
    "Return ONLY a JSON object (no markdown fences, no extra text) with this exact schema:\n"
    '{\n'
    '  "merchant_name": "string or null",\n'
    '  "receipt_date": "YYYY-MM-DD or null",\n'
    '  "total_amount": 0.0,\n'
    '  "currency": "PKR or detected currency code (MYR, USD, EUR, CHF, etc.)",\n'
    '  "line_items": [\n'
    '    {\n'
    '      "raw_text": "original line as seen on receipt",\n'
    '      "item_name": "clean canonical product name in English",\n'
    '      "quantity": 1.0,\n'
    '      "unit": "kg or g or ltr or ml or pcs or pkt or dzn",\n'
    '      "unit_price": 0.0,\n'
    '      "total_price": 0.0,\n'
    '      "category": "Groceries & Food",\n'
    '      "confidence_score": 0.9,\n'
    '      "bbox": {"ymin": 0.25, "xmin": 0.05, "ymax": 0.29, "xmax": 0.95}\n'
    '    }\n'
    '  ],\n'
    '  "ocr_quality": "high or medium or low",\n'
    '  "notes": "any issues or ambiguities"\n'
    '}\n\n'
    "Rules:\n"
    "1. Translate Roman Urdu to English: Atta=Wheat Flour, Doodh=Milk, Chawal=Rice, "
    "Cheeni=Sugar, Dahi=Yogurt, Ghee=Clarified Butter, Pyaz=Onion, Tamatar=Tomato, "
    "Aloo=Potato, Mitha=Sweet Melon, Palak=Spinach, Daal=Lentils, Gosht=Meat, "
    "Murg=Chicken, Sabzi=Vegetables.\n"
    "2. Use the rightmost amount column as total_price.\n"
    "3. For METRO-style receipts with columns [Qty, Price/MU, Price/Pack, Total Net, GST, Total], "
    "use the last Total column as total_price.\n"
    "4. confidence_score: 1.0=perfectly clear, 0.5=partially readable, 0.2=guessed.\n"
    "5. Skip items you cannot read at all.\n"
    "6. For physical store/grocery receipts: do NOT include subtotals, tax lines, or grand totals in line_items.\n"
    "7. For digital payment confirmations, bank transfers, or e-wallet screenshots (e.g. NayaPay, SadaPay, Easypaisa, JazzCash, Raast, banking apps):\n"
    "   - merchant_name is the recipient or beneficiary store/person (e.g. 'ZAM ZAM BIRYANI').\n"
    "   - receipt_date is the transaction date (e.g. '2026-10-16').\n"
    "   - total_amount is the grand total transferred or debited.\n"
    "   - line_items MUST contain item(s) representing the transaction: include the main payment amount (e.g. raw_text: 'Transferred to ZAM ZAM BIRYANI', item_name: 'Payment: ZAM ZAM BIRYANI', total_price: transfer amount) and any transaction fee if explicitly shown.\n"
    "   - category should be inferred from the beneficiary (e.g. 'ZAM ZAM BIRYANI' is 'Groceries & Food', electric/gas is 'Utilities & Bills').\n"
    "8. quantity defaults to 1.0 if not shown; unit defaults to pcs.\n"
    "9. category must be one of: Groceries & Food, Household & Cleaning, Personal Care, "
    "Health & Pharmacy, Snacks & Beverages, Utilities & Bills, Miscellaneous.\n"
    "10. bbox (strongly recommended): normalized bounding box [ymin, xmin, ymax, xmax] or "
    '{"ymin": float, "xmin": float, "ymax": float, "xmax": float} with coordinates between 0.0 and 1.0 spanning the item line.\n'
)


def is_available() -> bool:
    """Return True if the Gemini API key is configured."""
    return bool(getattr(settings, "gemini_api_key", ""))


def extract_receipt_data(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
) -> Optional[Dict[str, Any]]:
    """
    Send receipt image to Gemini and return the parsed JSON dict.

    Args:
        image_bytes: Raw bytes of the receipt image.
        mime_type:   MIME type ('image/jpeg' or 'image/png').

    Returns:
        Parsed dict with merchant_name, receipt_date, total_amount, line_items, etc.
        None on any failure.
    """
    if not is_available():
        logger.debug("Gemini client: no API key configured or google-genai not installed. Skipping.")
        return None

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        logger.warning("google-genai package not installed. Run: pip install google-genai")
        return None

    client = genai.Client(api_key=settings.gemini_api_key)
    part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

    # Candidate models in order of attempt (starts with configured model, falls back on high-demand 503s)
    candidates = [settings.gemini_model, "gemini-3.5-flash-lite", "gemini-3.7-flash", "gemini-3.8-flash"]
    seen = set()
    model_list = [m for m in candidates if not (m in seen or seen.add(m))]

    last_error: Optional[Exception] = None

    for model_name in model_list:
        try:
            logger.debug("Attempting receipt extraction with Gemini model: %s", model_name)
            response = client.models.generate_content(
                model=model_name,
                contents=[_RECEIPT_PROMPT, part],
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=4096,
                    response_mime_type="application/json",
                ),
            )

            raw_text = (response.text or "").strip()
            # Strip any markdown fences if present
            raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.MULTILINE)
            raw_text = re.sub(r"\s*```\s*$", "", raw_text, flags=re.MULTILINE)
            raw_text = raw_text.strip()

            parsed = json.loads(raw_text)
            parsed["_model_used"] = model_name
            logger.info(
                "Gemini (%s) extracted %d line items (quality=%s).",
                model_name,
                len(parsed.get("line_items", [])),
                parsed.get("ocr_quality", "?"),
            )
            return parsed

        except json.JSONDecodeError as exc:
            logger.warning("Gemini model %s returned non-JSON response: %s", model_name, exc)
            last_error = exc
            continue
        except Exception as exc:
            err_str = str(exc)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                logger.warning("Gemini model %s hit rate limit (429). Waiting 5s before next attempt...", model_name)
                time.sleep(5.0)
            else:
                logger.warning("Gemini API call to model %s failed: %s", model_name, exc)
            last_error = exc
            continue

    logger.error("All Gemini candidate models failed. Last error: %s", last_error)
    return None


def _normalize_bbox(raw_bbox: Any) -> Optional[Dict[str, float]]:
    """Helper to convert any bbox representation (dict, list, 0-1000 scale) into normalized 0.0-1.0 dict."""
    if not raw_bbox:
        return None
    ymin, xmin, ymax, xmax = None, None, None, None
    if isinstance(raw_bbox, dict):
        ymin = raw_bbox.get("ymin") if "ymin" in raw_bbox else raw_bbox.get("y_min")
        xmin = raw_bbox.get("xmin") if "xmin" in raw_bbox else raw_bbox.get("x_min")
        ymax = raw_bbox.get("ymax") if "ymax" in raw_bbox else raw_bbox.get("y_max")
        xmax = raw_bbox.get("xmax") if "xmax" in raw_bbox else raw_bbox.get("x_max")
    elif isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) >= 4:
        ymin, xmin, ymax, xmax = raw_bbox[0], raw_bbox[1], raw_bbox[2], raw_bbox[3]

    if ymin is None or ymax is None:
        return None

    try:
        y1, x1, y2, x2 = float(ymin), float(xmin or 0.0), float(ymax), float(xmax or 1.0)
        # If coordinates are given in 0-1000 scale (standard Gemini 2D box scale)
        if y2 > 1.0 or x2 > 1.0:
            if y2 <= 1000.0 and x2 <= 1000.0:
                y1, x1, y2, x2 = y1 / 1000.0, x1 / 1000.0, y2 / 1000.0, x2 / 1000.0
        return {
            "ymin": round(max(0.0, min(1.0, y1)), 4),
            "xmin": round(max(0.0, min(1.0, x1)), 4),
            "ymax": round(max(0.0, min(1.0, y2)), 4),
            "xmax": round(max(0.0, min(1.0, x2)), 4),
        }
    except (ValueError, TypeError):
        return None


def gemini_result_to_line_items(
    gemini_data: Dict[str, Any],
) -> List[LineItemCreate]:
    """
    Convert Gemini JSON response dict into LineItemCreate objects
    compatible with the rest of the ingestion pipeline.
    """
    items: List[LineItemCreate] = []
    for raw in gemini_data.get("line_items", []):
        try:
            bbox = _normalize_bbox(raw.get("bbox"))
            item = LineItemCreate(
                raw_text=str(raw.get("raw_text", "")),
                item_name=str(raw.get("item_name", "Unknown Item")).strip(),
                quantity=float(raw.get("quantity", 1.0)),
                unit=str(raw.get("unit", "pcs")).lower(),
                unit_price=float(raw.get("unit_price", 0.0)),
                total_price=float(raw.get("total_price", 0.0)),
                confidence_score=float(raw.get("confidence_score", 0.85)),
                category=str(raw.get("category", "Miscellaneous")),
                is_verified=False,
                bbox=bbox,
            )
            # Skip zero-price items with very low confidence (likely noise)
            if item.total_price <= 0 and item.unit_price <= 0 and item.confidence_score < 0.5:
                continue
            items.append(item)
        except (ValueError, TypeError) as exc:
            logger.debug("Skipping malformed Gemini line item %s: %s", raw, exc)
    return items


def extract_and_parse(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
) -> Tuple[List[LineItemCreate], Optional[Dict[str, Any]]]:
    """
    Convenience wrapper: extract + convert in one call.

    Returns:
        (line_items, metadata_dict)
        metadata_dict includes: merchant_name, receipt_date, total_amount,
        ocr_quality, notes, currency. None on failure.
    """
    data = extract_receipt_data(image_bytes, mime_type)
    if not data:
        return [], None
    return gemini_result_to_line_items(data), data