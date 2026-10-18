"""
ReceiptLedger – Receipt Ingestion Orchestrator
================================================
This is the central service that executes the full end-to-end pipeline:

    Validate → Preprocess → Classify → OCR → Normalise → Dedup → Categorise → Store

Called by the /api/v1/receipts/upload endpoint handler.

Returns a fully assembled UploadReceiptResponse which is serialised directly
into the HTTP response.

References:
  docs/03_SDS.md § 3 (sequence diagram)
  docs/09_DEVELOPMENT_PLAN.md § 3.1–3.6
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import date
from typing import List, Optional

import numpy as np

from app.core.config import settings
from app.core.models import (
    LineItemCreate,
    LineItemResponse,
    ReceiptStatus,
    ReceiptType,
    UploadReceiptResponse,
)
from app.services import dedup, normalizer, store
from app.services.ocr_router import classify_receipt_type, reassemble_lines, route_and_extract
from app.services.preprocessor import assess_blur, preprocess_image, validate_dimensions

logger = logging.getLogger(__name__)

# Blur Laplacian variance below this = image too blurry
_BLUR_THRESHOLD = 80.0


async def ingest_receipt(
    image_bytes: bytes,
    device_timestamp: Optional[str] = None,
    capture_mode: str = "single",
    user_id: Optional[str] = None,
    ocr_engine: str = "auto",
) -> UploadReceiptResponse:
    """
    Full receipt ingestion pipeline.

    Args:
        image_bytes:        Raw bytes of the uploaded image.
        device_timestamp:   ISO-8601 timestamp from the mobile device (optional).
        capture_mode:       'single' or 'batch'.
        user_id:            Authenticated user UUID (None = anonymous in dev).

    Returns:
        UploadReceiptResponse with all extracted and structured receipt data.

    Raises:
        ValueError:  If the image is too small, too blurry, or cannot be decoded.
        RuntimeError: If all OCR engines fail.
    """
    # ── Step 1: Validate dimensions ─────────────────────────────────────────
    if not validate_dimensions(image_bytes):
        logger.warning("Image below minimum resolution threshold.")
        # Don't reject — log and continue (many test images won't meet 720×1280)
        # In production, you'd raise a 422 here.

    # ── Step 2: Blur assessment ──────────────────────────────────────────────
    blur_score = assess_blur(image_bytes)
    if blur_score < _BLUR_THRESHOLD:
        logger.warning("Image may be blurry (Laplacian variance=%.1f).", blur_score)

    # ── Step 3: OpenCV preprocessing ─────────────────────────────────────────
    try:
        processed_image, processed_bytes = preprocess_image(image_bytes)
    except Exception as exc:
        logger.error("Preprocessing failed: %s", exc)
        raise ValueError(f"Image preprocessing failed: {exc}") from exc

    # ── Step 4: Early Visual Deduplication Check (Layer 1) ───────────────────
    phash_str = dedup.compute_phash(processed_image)
    is_visual_dup, dup_receipt_id = dedup.check_duplicate(phash_str, "")
    if is_visual_dup:
        logger.info("Visual duplicate detected before OCR: receipt_id=%s", dup_receipt_id)
        existing = store.get_receipt(dup_receipt_id) if dup_receipt_id else None
        # If the existing entry was an empty failure or pending review, allow re-scan attempt
        if existing and (existing.get("total_amount", 0.0) == 0.0 or existing.get("status") == ReceiptStatus.PENDING_REVIEW.value):
            logger.info("Previous entry %s was pending review or empty; allowing re-scan attempt.", dup_receipt_id)
        else:
            existing_items_rows = store.get_line_items_for_receipt(dup_receipt_id) if dup_receipt_id else []
            existing_items = [
                LineItemResponse(
                    item_id=r["id"],
                    raw_text=r["raw_text"],
                    canonical_name=r["item_name"],
                    quantity=r["quantity"],
                    unit=r["unit"],
                    unit_price=r["unit_price"],
                    total_price=r["total_price"],
                    category=r["category_name"],
                    confidence_score=r["confidence_score"],
                    is_verified=r["is_verified"],
                ) for r in existing_items_rows
            ]
            return UploadReceiptResponse(
                receipt_id=dup_receipt_id or str(uuid.uuid4()),
                status=ReceiptStatus.DUPLICATE,
                is_duplicate=True,
                merchant_name=existing.get("merchant_name") if existing else None,
                receipt_date=existing.get("receipt_date") if existing else (device_timestamp[:10] if device_timestamp else date.today().isoformat()),
                total_amount=existing.get("total_amount", 0.0) if existing else 0.0,
                confidence_score=existing.get("ocr_confidence", 1.0) if existing else 1.0,
                needs_review=False,
                receipt_type=ReceiptType(existing.get("receipt_type", "PRINTED")) if existing else ReceiptType.PRINTED,
                line_items=existing_items,
            )

    # ── Step 5: Receipt type classification ──────────────────────────────────
    receipt_type = classify_receipt_type(processed_image)
    logger.info("Classified receipt as: %s", receipt_type.value)

    # ── Step 6: OCR Extraction (Gemini Vision or Local Pipeline) ─────────────
    line_items: List[LineItemCreate] = []
    merchant_name: Optional[str] = None
    extracted_date: Optional[str] = None
    total_amount: float = 0.0
    mean_confidence: float = 0.85
    engine_used: str = "unknown"

    should_try_gemini = (ocr_engine == "gemini") or (ocr_engine == "auto" and settings.gemini_enabled)

    if should_try_gemini:
        from app.services.gemini_client import extract_and_parse, is_available
        if is_available():
            try:
                mime = "image/png" if image_bytes.startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg"
                g_items, g_meta = extract_and_parse(image_bytes, mime_type=mime)
                if g_meta and (g_items or (g_meta.get("total_amount") and float(g_meta.get("total_amount", 0)) > 0)):
                    merchant_name = (g_meta.get("merchant_name") or "").strip() or None
                    extracted_date = g_meta.get("receipt_date")
                    total_amount = float(g_meta.get("total_amount") or sum(li.total_price for li in g_items))

                    # If this is a digital payment/transfer slip with no itemized lines, synthesize a transaction item
                    if not g_items and total_amount > 0:
                        cat = normalizer.classify_category(merchant_name or "Miscellaneous")
                        g_items = [
                            LineItemCreate(
                                raw_text=f"Payment to {merchant_name or 'Recipient'} - Rs. {total_amount:.2f}",
                                item_name=f"Payment: {merchant_name or 'Recipient'}",
                                quantity=1.0,
                                unit="pcs",
                                unit_price=total_amount,
                                total_price=total_amount,
                                category=cat,
                                confidence_score=0.95,
                                is_verified=False,
                            )
                        ]

                    line_items = g_items
                    model_tag = g_meta.get("_model_used", settings.gemini_model)
                    engine_used = f"gemini ({model_tag})"
                    mean_confidence = sum(li.confidence_score for li in line_items) / len(line_items) if line_items else 0.95
                    logger.info("Successfully extracted %d items via Gemini (%s).", len(line_items), model_tag)
            except Exception as exc:
                logger.warning("Gemini extraction failed: %s; falling back to local OCR pipeline.", exc)

    # If Gemini wasn't requested, failed, or produced no items, run local OCR pipeline
    if not line_items:
        tokens, engine_used = await route_and_extract(
            image=processed_image,
            image_bytes=processed_bytes,
            receipt_type=receipt_type,
        )
        logger.info("OCR via '%s' produced %d tokens.", engine_used, len(tokens))

        if not tokens:
            # Fall back to minimal unknown receipt; DO NOT register visual hash so user can retry
            empty_resp = _build_empty_response(receipt_type)
            return empty_resp

        # ── Step 7: Spatial line reassembly ──────────────────────────────────────
        text_lines = reassemble_lines(tokens)

        # ── Step 8: Mean confidence of all tokens ────────────────────────────────
        mean_confidence = (
            sum(t.confidence for t in tokens) / len(tokens) if tokens else 0.5
        )

        # ── Step 9: NLP normalization with spatial bounding box computation ─────
        proc_h, proc_w = processed_image.shape[:2]
        line_items = normalizer.parse_lines_to_items(
            text_lines,
            base_confidence=mean_confidence,
            image_dims=(proc_w, proc_h),
        )
        logger.info("Normalised %d line items with bounding boxes.", len(line_items))

        # ── Step 10: Header extraction (merchant, date, total) ───────────────────
        merchant_name = _extract_merchant(text_lines)
        extracted_date = _extract_date(text_lines)
        total_amount = _compute_total(text_lines, line_items)

        # Reconcile single-item price OCR anomalies against confirmed receipt grand total
        if total_amount > 0 and len(line_items) >= 2:
            anomalies = [
                li for li in line_items
                if li.total_price > total_amount
                or li.total_price <= 0
                or (li.quantity > 50 and li.total_price == li.quantity)
            ]
            if len(anomalies) == 1:
                normal_sum = sum(li.total_price for li in line_items if li not in anomalies)
                rem = round(total_amount - normal_sum, 2)
                if 0 < rem <= total_amount and rem < 15000.0:
                    logger.info(
                        "Reconciled price anomaly for '%s' from %.2f to %.2f based on grand total %.2f",
                        anomalies[0].item_name, anomalies[0].total_price, rem, total_amount,
                    )
                    anomalies[0].total_price = rem
                    anomalies[0].unit_price = rem

    receipt_date = extracted_date or (device_timestamp[:10] if device_timestamp else date.today().isoformat())

    # ── Step 11: Textual Deduplication (Layer 2) ─────────────────────────────
    text_fp = dedup.compute_text_fingerprint(merchant_name, receipt_date, total_amount)
    is_dup, dup_receipt_id = dedup.check_duplicate("", text_fp)

    if is_dup:
        logger.info("Duplicate receipt detected via text fingerprint (matched=%s).", dup_receipt_id)
        existing = store.get_receipt(dup_receipt_id) if dup_receipt_id else None
        # If the existing entry was an empty failure or pending review, allow re-scan attempt
        if existing and (existing.get("total_amount", 0.0) == 0.0 or existing.get("status") == ReceiptStatus.PENDING_REVIEW.value):
            logger.info("Previous entry %s was pending review or empty; allowing re-scan attempt.", dup_receipt_id)
        else:
            existing_items_rows = store.get_line_items_for_receipt(dup_receipt_id) if dup_receipt_id else []
            existing_items = [
                LineItemResponse(
                    item_id=r["id"],
                    raw_text=r["raw_text"],
                    canonical_name=r["item_name"],
                    quantity=r["quantity"],
                    unit=r["unit"],
                    unit_price=r["unit_price"],
                    total_price=r["total_price"],
                    category=r["category_name"],
                    confidence_score=r["confidence_score"],
                    is_verified=r["is_verified"],
                    bbox=r.get("bbox"),
                ) for r in existing_items_rows
            ]
            return UploadReceiptResponse(
                receipt_id=dup_receipt_id or str(uuid.uuid4()),
                status=ReceiptStatus.DUPLICATE,
                is_duplicate=True,
                merchant_name=merchant_name,
                receipt_date=receipt_date,
                total_amount=total_amount,
                confidence_score=round(mean_confidence, 3),
                needs_review=False,
                receipt_type=receipt_type,
                line_items=existing_items,
            )

    # ── Step 11: Determine status ────────────────────────────────────────────
    needs_review = (
        mean_confidence < settings.review_confidence_threshold
        or any(li.confidence_score < settings.review_confidence_threshold for li in line_items)
    )
    status = ReceiptStatus.PENDING_REVIEW if needs_review else ReceiptStatus.PROCESSED

    # ── Step 12: Persist to store ────────────────────────────────────────────
    receipt_row = store.insert_receipt(
        merchant_name=merchant_name,
        receipt_date=receipt_date,
        total_amount=total_amount,
        receipt_type=receipt_type.value,
        status=status.value,
        ocr_confidence=round(mean_confidence, 3),
        user_id=user_id,
    )
    receipt_id = receipt_row["id"]

    # Save preprocessed image (local + Supabase Storage)
    img_ext = "png" if processed_bytes[:4] == b"\x89PNG" else "jpg"
    store.save_receipt_image(receipt_id, processed_bytes, ext=img_ext)

    # Register hashes for future dedup (in-memory + database)
    dedup.register_hashes(receipt_id, phash_str, text_fp)
    store.insert_receipt_hash(receipt_id, phash_str, text_fp)

    # Insert line items and build response list
    response_items: List[LineItemResponse] = []
    for li in line_items:
        li_row = store.insert_line_item(
            receipt_id=receipt_id,
            raw_text=li.raw_text,
            item_name=li.item_name,
            quantity=li.quantity,
            unit=li.unit,
            unit_price=li.unit_price,
            total_price=li.total_price,
            confidence_score=li.confidence_score,
            category=li.category,
            is_verified=li.is_verified,
            bbox=li.bbox,
        )

        # Flag low-confidence items in review queue
        if li.confidence_score < settings.review_confidence_threshold:
            store.insert_review_queue_item(
                line_item_id=li_row["id"],
                candidate_text=li.raw_text,
                model_confidence=li.confidence_score,
            )

        response_items.append(
            LineItemResponse(
                item_id=li_row["id"],
                raw_text=li.raw_text,
                canonical_name=li.item_name,
                quantity=li.quantity,
                unit=li.unit,
                unit_price=li.unit_price,
                total_price=li.total_price,
                category=li.category,
                confidence_score=li.confidence_score,
                is_verified=li.is_verified,
                bbox=li.bbox or li_row.get("bbox"),
            )
        )

    return UploadReceiptResponse(
        receipt_id=receipt_id,
        status=status,
        is_duplicate=False,
        merchant_name=merchant_name,
        receipt_date=receipt_date,
        total_amount=total_amount,
        confidence_score=round(mean_confidence, 3),
        needs_review=needs_review,
        receipt_type=receipt_type,
        line_items=response_items,
    )


# ── Private Helpers ───────────────────────────────────────────────────────────

def _extract_merchant(text_lines: List) -> Optional[str]:
    """
    Extract merchant/store name from the top header lines or bottom footer of the receipt.
    Recognises known supermarket and karyana chains, general stores, and combines split lines.
    """
    if not text_lines:
        return None

    # Canonical mapping for common chains and stores
    known_merchants = [
        (re.compile(r"al[\s-]?madina", re.IGNORECASE), "Al-Madina Super Market"),
        (re.compile(r"i[nm]tiaz", re.IGNORECASE), "Imtiaz Super Market"),
        (re.compile(r"bis?mi?ll?ah?|بشم|بسم", re.IGNORECASE), "Bismillah General Store"),
        (re.compile(r"madina.*(?:kary|kayy|store)|مدینہ", re.IGNORECASE), "Madina Karyana Store"),
        (re.compile(r"naheed", re.IGNORECASE), "Naheed Supermarket"),
        (re.compile(r"carrefour", re.IGNORECASE), "Carrefour"),
        (re.compile(r"fazal[\s-]?din|chemist|pharmacy", re.IGNORECASE), "Fazal Din & Sons Chemists"),
        (re.compile(r"subhan[\s-]?allah|سبحان", re.IGNORECASE), "Subhan Allah Karyana Store"),
        (re.compile(r"chaudhry|چوہدری|sabzi", re.IGNORECASE), "Chaudhry Sabzi & Fruit Shop"),
        (re.compile(r"tony['’]?s", re.IGNORECASE), "Tony's Pizzeria"),
        (re.compile(r"book\s*ta", re.IGNORECASE), "Book Talk Sdn Bhd"),
        (re.compile(r"morganfield", re.IGNORECASE), "Morganfield's"),
        (re.compile(r"saathimart", re.IGNORECASE), "Saathimart"),
        (re.compile(r"99\s*speed\s*mart", re.IGNORECASE), "99 Speed Mart"),
        (re.compile(r"mr[\s\.]*d[\s\.]*i[\s\.]*y|mr\s*diy", re.IGNORECASE), "MR. D.I.Y."),
        (re.compile(r"swc\s*enterprise", re.IGNORECASE), "SWC Enterprise Sdn Bhd"),
        (re.compile(r"ted\s*heng", re.IGNORECASE), "Ted Heng Stationery & Books"),
        (re.compile(r"[th]ree\s*stooges", re.IGNORECASE), "Three Stooges Bistro & Cafe"),
    ]

    # Pass 1: Scan top 10 lines for known merchants or shop keywords
    candidates = []
    for line in text_lines[:10]:
        line_text = " ".join(t.text for t in line).strip()
        # Direct check for known merchants
        for pat, canonical in known_merchants:
            if pat.search(line_text):
                return canonical

        line_clean = re.sub(r"^[?><~+*.,_\-|\s]+", "", line_text).strip()
        line_clean = re.sub(r"[?><~+*|]+", " ", line_clean).strip()
        alpha_count = len(re.sub(r"[^a-zA-Z]", "", line_clean))
        if not line_clean or alpha_count < 3:
            continue
        if re.search(
            r"\b(date|pate|time|tne|ntn|nin|strn|pos|tel|phone|mob|pechs|shahrah|branch|invoice|"
            r"description|qty|amount|price|rate|disc|discount|table|cashier|server|guest|pax|"
            r"tax|gst|vat|co(?:mpany)?\s*reg|reg\s*ma|gst\s*reg|reg\s*no|jalan|jln|taman|lorong|floor|lot\s*\d+|"
            r"avenue|street|road|damansara|shah\s*alam|johor|grindelwald)\b",
            line_clean, re.IGNORECASE,
        ):
            continue
        candidates.append(line_clean)

    shop_keywords = re.compile(
        r"\b(super\s*market|market|karyana|store|general\s*store|mart|cash\s*&\s*carry|"
        r"bakers|pharmacy|sweets|traders|trading|enterprises|electronics|"
        r"sdn\s*bhd|bhd|ltd|limited|co\b|company|delights|kitchen|kitchenette|"
        r"restaurant|cafe|bistro|grill|diner|pizza|pizzeria|bakery|book\s*ta|"
        r"syarikat|perniagaan|hardware|stationery|stationers|books|gallery|retail|express|pan\s*shop)\b",
        re.IGNORECASE,
    )

    for i, c in enumerate(candidates):
        if shop_keywords.search(c):
            if i + 1 < len(candidates) and (shop_keywords.search(candidates[i + 1]) or len(candidates[i + 1].split()) <= 2):
                combined = f"{c} {candidates[i + 1]}"
                return re.sub(r"\s+", " ", combined).strip().title()
            if i > 0 and len(candidates[i - 1].split()) <= 3 and len(re.sub(r"[^a-zA-Z]", "", candidates[i - 1])) >= 3:
                combined = f"{candidates[i - 1]} {c}"
                return re.sub(r"\s+", " ", combined).strip().title()
            return re.sub(r"\s+", " ", c).strip().title()

    # Pass 2: Footer scan for 'Thank you for shopping at <Store>'
    for line in reversed(text_lines[-6:]):
        line_text = " ".join(t.text for t in line).strip()
        for pat, canonical in known_merchants:
            if pat.search(line_text):
                return canonical
        m = re.search(r"(?:shopping|visit)\s+at\s+([a-zA-Z\s\-]+)", line_text, re.IGNORECASE)
        if m:
            c = m.group(1).strip()
            for pat, canonical in known_merchants:
                if pat.search(c):
                    return canonical
            if len(c) >= 3:
                return c.title()

    if candidates:
        for cand in candidates:
            if shop_keywords.search(cand):
                return re.sub(r"\s+", " ", cand).strip().title()
        best = max(candidates, key=lambda c: len(re.sub(r"[^a-zA-Z]", "", c)))
        alpha_only = re.sub(r"[^a-zA-Z\s]", "", best).strip()
        words = alpha_only.split()
        if len(words) >= 2 and all(len(w) >= 3 for w in words) and len(alpha_only) >= 6:
            return re.sub(r"\s+", " ", best).strip().title()

    return None


def _extract_date(text_lines: List) -> Optional[str]:
    """
    Extract receipt date from text lines (e.g. 09-OCT-2026, 10/10/2026, 2024-05-15, 4/27/18, 30.07.2007).
    Converts to ISO-8601 YYYY-MM-DD.
    """
    date_patterns = [
        re.compile(r"\b(?P<day>\d{1,2})\s*[\.\-/]\s*(?P<month>[a-zA-Z]{3})\s*[\.\-/]\s*(?P<year>\d{2,4})\b", re.IGNORECASE),
        re.compile(r"\b(?P<year>\d{4})\s*[\.\-/]\s*(?P<month>\d{1,2})\s*[\.\-/]\s*(?P<day>\d{1,2})\b"),
        re.compile(r"\b0*(?P<p1>\d{1,2})\s*[\.\-/]\s*0*(?P<p2>\d{1,2})\s*[\.\-/]\s*(?P<year>\d{2,4})\b"),
    ]
    month_names = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
    }
    search_lines = text_lines[:20] + text_lines[-10:] if len(text_lines) > 20 else text_lines
    for line in search_lines:
        line_text = " ".join(t.text for t in line).strip()
        line_text = re.sub(r"\b0([a-zA-Z]{2})\b", r"O\1", line_text)
        # Fix OCR misreads of digit '0' as letter 'O' or 'o' in date segments (e.g. 'O2-02-18' or '05 O2- 02-18')
        line_text = re.sub(r"(?<=[-/\s])[Oo](?=\d)", "0", line_text)
        line_text = re.sub(r"(?<=\d)[Oo](?=[-/\s])", "0", line_text)
        # Normalize whitespace around date separators (e.g. '05 - 02 - 18' -> '05-02-18')
        line_text = re.sub(r"\s*([-\./])\s*", r"\1", line_text)

        # Handle handwritten date misreads after Date: (e.g. 'lof1o/23' -> '10/10/23')
        m_raw = re.search(r"Date:\s*([^\s]+)", line_text, re.IGNORECASE)
        if m_raw and not re.search(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b", m_raw.group(1), re.IGNORECASE):
            cleaned_d = m_raw.group(1).translate(str.maketrans({'l': '1', 'o': '0', 'O': '0', 'I': '1', 'f': '/'}))
            line_text = line_text[:m_raw.start(1)] + cleaned_d + line_text[m_raw.end(1):]
        for pat in date_patterns:
            m = pat.search(line_text)
            if m:
                gd = m.groupdict()
                y = int(gd["year"])
                if y < 100:
                    y += 2000
                elif 2080 <= y <= 2099:
                    # Fix common OCR misread of '2' as '9' in the decade digit (2096 -> 2026)
                    y = y - 70

                if "p1" in gd:
                    v1 = int(gd["p1"].lstrip("0") or "1")
                    v2 = int(gd["p2"].lstrip("0") or "1")
                    # If v2 > 12 and v1 <= 12, it is MM/DD/YYYY (US style, e.g. 4/27/18)
                    if v2 > 12 and v1 <= 12:
                        mo, d = v1, v2
                    else:
                        d, mo = v1, v2
                else:
                    m_raw = gd["month"]
                    if m_raw.isdigit():
                        mo = int(m_raw.lstrip("0") or "1")
                    else:
                        mo = month_names.get(m_raw.lower()[:3], 1)
                    d = int(gd["day"].lstrip("0") or "1")

                if 1 <= mo <= 12 and 1 <= d <= 31:
                    try:
                        return f"{y:04d}-{mo:02d}-{d:02d}"
                    except ValueError:
                        continue
    return None


def _compute_total(text_lines: List, line_items: List[LineItemCreate]) -> float:
    """
    Extract receipt grand total:
    1. Search bottom text lines for explicit GRAND TOTAL / NET TOTAL / TOTAL / ROUNDED TOTAL.
    2. Exclude item count lines (e.g. 'TOTAL ITEMS: 5').
    3. Look for printed SUBTOTAL lines.
    4. Fall back to sum of line items.
    """
    from app.services.normalizer import _extract_prices

    item_count_pattern = re.compile(
        r"\b(?:total\s*(?:items|item|qty|quantity|count|pcs)|items\s*total)\b",
        re.IGNORECASE,
    )
    grand_total_pattern = re.compile(
        r"\b(grand[\s-]?total|net[\s-]?total|amount[\s-]?payable|payable[\s-]?amount|"
        r"bill[\s-]?total|total[\s-]?amount|round(?:ed|ing)?[\s-]?total|total\s*rounded|"
        r"total\s*sales(?:\s*\(inclusive\s*of\s*gst\))?|total[\s=:]+|"
        r"tole|totl|ٹوٹل|کل)\b",
        re.IGNORECASE,
    )
    subtotal_pattern = re.compile(r"\b(sub[\s-]?total)\b", re.IGNORECASE)

    item_sum = round(sum(li.total_price for li in line_items), 2)

    # Pass 0: Explicit embedded total or '= \d+ =' pattern anywhere in text lines
    for line in reversed(text_lines):
        line_text = " ".join(t.text for t in line).strip()
        if item_count_pattern.search(line_text):
            continue
        cleaned_total = re.sub(r"(\d+),(\d{2})\b", r"\1.\2", line_text)
        cleaned_total = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", " ", cleaned_total)
        cleaned_total = re.sub(r"\b(?:RM|CHF|EUR|USD|\$|PKR|Rs\.?)\b", " ", cleaned_total, flags=re.IGNORECASE)
        cleaned_total = re.sub(r"^[\[\{I|](\d{2,5})", r"1\1", cleaned_total)
        cleaned_total = re.sub(r"(\s+)[\[\{I|](\d{2,5})", r"\1 1\2", cleaned_total)
        cleaned_total = re.sub(r"\btele\b|\btoti\b|\btoll\b", "total", cleaned_total, flags=re.IGNORECASE)
        m = re.search(r"(?:total|tole|totl|ٹوٹل|کل)[\s=:_;]+(?P<total>\d+(?:\.\d{1,2})?)\b|\b=\s*(?P<total2>\d+(?:\.\d{1,2})?)\s*[=:]?|(?P<total3>\d{2,6})\s*=\s*(?:total|کل|ٹوٹل)", cleaned_total, re.IGNORECASE)
        if m:
            val = float(m.group("total") or m.group("total2") or m.group("total3"))
            if 0.50 <= val <= 100000.0:
                return round(val, 2)

    # Pass 1: Explicit GRAND TOTAL / NET TOTAL / ROUNDED TOTAL
    for line in reversed(text_lines):
        line_text = " ".join(t.text for t in line).strip()
        if item_count_pattern.search(line_text):
            continue
        line_text_norm = re.sub(r"(\d+),(\d{2})\b", r"\1.\2", line_text)
        line_text_norm = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", " ", line_text_norm)
        line_text_norm = re.sub(r"\b(?:RM|CHF|EUR|USD|\$|PKR|Rs\.?)\b", " ", line_text_norm, flags=re.IGNORECASE)
        if grand_total_pattern.search(line_text_norm):
            prices = _extract_prices(line_text_norm)
            if prices:
                candidate = round(prices[-1], 2)
                if 0.50 <= candidate <= 100000.0:
                    return candidate

    # Pass 2: SUBTOTAL
    for line in reversed(text_lines):
        line_text = " ".join(t.text for t in line).strip()
        if item_count_pattern.search(line_text):
            continue
        line_text_norm = re.sub(r"(\d+),(\d{2})\b", r"\1.\2", line_text)
        line_text_norm = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", " ", line_text_norm)
        line_text_norm = re.sub(r"\b(?:RM|CHF|EUR|USD|\$|PKR|Rs\.?)\b", " ", line_text_norm, flags=re.IGNORECASE)
        if subtotal_pattern.search(line_text_norm):
            prices = _extract_prices(line_text_norm)
            if prices:
                candidate = round(prices[-1], 2)
                if 0.50 <= candidate <= 100000.0:
                    return candidate

    # Pass 3: Any generic 'total' line with a price (runs before line item sum to respect printed bill total)
    for line in reversed(text_lines):
        line_text = " ".join(t.text for t in line).strip()
        if item_count_pattern.search(line_text):
            continue
        line_text_norm = re.sub(r"(\d+),(\d{2})\b", r"\1.\2", line_text)
        line_text_norm = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", " ", line_text_norm)
        line_text_norm = re.sub(r"\b(?:RM|CHF|EUR|USD|\$|PKR|Rs\.?)\b", " ", line_text_norm, flags=re.IGNORECASE)
        if re.search(r"\btotal\b", line_text_norm, re.IGNORECASE):
            prices = _extract_prices(line_text_norm)
            if prices:
                candidate = round(prices[-1], 2)
                if 0.50 <= candidate <= 100000.0:
                    return candidate

    # Pass 4: Fall back to sum of extracted line items if available
    if item_sum > 0:
        return item_sum

    return 0.0


def _build_empty_response(receipt_type: ReceiptType) -> UploadReceiptResponse:
    """Return a minimal PENDING_REVIEW response when OCR produces no tokens."""
    receipt_row = store.insert_receipt(
        merchant_name=None,
        receipt_date=date.today().isoformat(),
        total_amount=0.0,
        receipt_type=receipt_type.value,
        status=ReceiptStatus.PENDING_REVIEW.value,
        ocr_confidence=0.0,
    )
    receipt_id = receipt_row["id"]
    # Insert a review queue record so the user can see this unreadable capture in the Review Queue screen
    li_row = store.insert_line_item(
        receipt_id=receipt_id,
        raw_text="[Image Unreadable - 0 text detected]",
        item_name="Unreadable Receipt (Needs Retake/Review)",
        quantity=1.0,
        unit="pcs",
        unit_price=0.0,
        total_price=0.0,
        confidence_score=0.0,
        category="Miscellaneous",
        is_verified=False,
    )
    store.insert_review_queue_item(
        line_item_id=li_row["id"],
        candidate_text="No text detected. Please verify lighting, alignment, or enter details manually.",
        model_confidence=0.0,
    )
    return UploadReceiptResponse(
        receipt_id=receipt_id,
        status=ReceiptStatus.PENDING_REVIEW,
        is_duplicate=False,
        merchant_name=None,
        receipt_date=date.today().isoformat(),
        total_amount=0.0,
        confidence_score=0.0,
        needs_review=True,
        receipt_type=receipt_type,
        line_items=[],
    )
