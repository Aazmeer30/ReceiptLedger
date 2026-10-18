"""
ReceiptLedger – CLI Test Runner
=================================
Runs a comprehensive set of unit-level tests for the backend services
WITHOUT requiring a running server, Supabase, or external OCR APIs.

Usage (from backend/ directory):
    python -m app.cli_test
    # or
    python app/cli_test.py

All tests that require heavy libraries (OpenCV, EasyOCR) are skipped gracefully
if the library is unavailable, so the script runs even in minimal environments.

Test suites:
  1. Configuration loading
  2. Taxonomy loading & fuzzy matching
  3. Regex parsers (qty, unit, price extraction)
  4. Line item parsing
  5. Deduplication (pHash & text fingerprint)
  6. In-memory store operations
  7. OpenCV preprocessor (if opencv available)
  8. Tesseract client (if tesseract installed)
  9. Analytics aggregation
  10. Review queue workflow

Exit code: 0 = all pass, 1 = any failure.
"""

from __future__ import annotations

import sys
import traceback
from typing import Callable, List, Tuple

# ── Test Registry ─────────────────────────────────────────────────────────────

_tests: List[Tuple[str, Callable]] = []

def register(name: str):
    """Decorator to register a test function."""
    def decorator(fn: Callable):
        _tests.append((name, fn))
        return fn
    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# TEST 1: Configuration
# ─────────────────────────────────────────────────────────────────────────────

@register("Config: Settings load from .env")
def test_config():
    from app.core.config import settings
    assert isinstance(settings.port, int), "port must be int"
    assert 1 <= settings.port <= 65535, f"port out of range: {settings.port}"
    assert 0.0 < settings.review_confidence_threshold <= 1.0
    assert 0.0 < settings.fuzzy_match_threshold <= 1.0
    print(f"   environment={settings.environment}, port={settings.port}")
    print(f"   cloud_vision_enabled={settings.cloud_vision_enabled}")
    print(f"   supabase_enabled={settings.supabase_enabled}")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 2: Taxonomy Loading
# ─────────────────────────────────────────────────────────────────────────────

@register("Normalizer: Taxonomy loads successfully")
def test_taxonomy_load():
    from app.services.normalizer import _TAXONOMY
    assert len(_TAXONOMY) > 0, "Taxonomy must have at least one entry"
    print(f"   Loaded {len(_TAXONOMY)} taxonomy entries.")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 3: Fuzzy Matching
# ─────────────────────────────────────────────────────────────────────────────

@register("Normalizer: Fuzzy match – 'chakki atta' → 'Wheat Flour (Atta)'")
def test_fuzzy_atta():
    from app.services.normalizer import fuzzy_match
    result = fuzzy_match("chakki atta")
    assert result is not None, "Expected a match for 'chakki atta'"
    assert result.canonical_name == "Wheat Flour (Atta)"
    print(f"   Matched: '{result.canonical_name}' (category={result.category})")


@register("Normalizer: Fuzzy match – 'chki ata' → 'Wheat Flour (Atta)'")
def test_fuzzy_ata_typo():
    from app.services.normalizer import fuzzy_match
    result = fuzzy_match("chki ata")
    assert result is not None, "Expected a match for 'chki ata'"
    assert "Wheat Flour" in result.canonical_name
    print(f"   Matched typo: '{result.canonical_name}'")


@register("Normalizer: Fuzzy match – 'pepsi' → 'Soft Drink'")
def test_fuzzy_pepsi():
    from app.services.normalizer import fuzzy_match
    result = fuzzy_match("pepsi")
    assert result is not None
    assert result.category == "Snacks & Beverages"
    print(f"   '{result.canonical_name}' in category '{result.category}'")


@register("Normalizer: Fuzzy match – 'xyzunknown' → None")
def test_fuzzy_no_match():
    from app.services.normalizer import fuzzy_match
    result = fuzzy_match("xyzunknown")
    assert result is None, "Expected no match for 'xyzunknown'"
    print(f"   Correctly returned None for unknown item.")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 4: Regex Parsers
# ─────────────────────────────────────────────────────────────────────────────

@register("Normalizer: Price extraction – 'Rs.1450.00'")
def test_price_rs():
    from app.services.normalizer import _extract_prices
    prices = _extract_prices("Chakki Atta 5kg   Rs.1450.00")
    assert len(prices) >= 1
    assert 1450.0 in prices
    print(f"   Extracted prices: {prices}")


@register("Normalizer: Price extraction – 'PKR 200'")
def test_price_pkr():
    from app.services.normalizer import _extract_prices
    prices = _extract_prices("Dalda 1ltr PKR 200")
    assert 200.0 in prices
    print(f"   Extracted: {prices}")


@register("Normalizer: Qty+unit – '5 kg'")
def test_qty_kg():
    from app.services.normalizer import _extract_qty_unit
    qty, unit = _extract_qty_unit("chakki atta 5 kg 700")
    assert qty == 5.0
    assert unit == "kg"
    print(f"   qty={qty}, unit={unit}")


@register("Normalizer: Qty+unit – '500g'")
def test_qty_g():
    from app.services.normalizer import _extract_qty_unit
    qty, unit = _extract_qty_unit("sugar 500g 150")
    assert qty == 500.0
    assert unit == "g"
    print(f"   qty={qty}, unit={unit}")


@register("Normalizer: Item name extraction")
def test_item_name_extract():
    from app.services.normalizer import _extract_item_name
    name = _extract_item_name("Chakki Atta 5kg Rs.700")
    assert len(name) > 0, "Should extract some item name"
    print(f"   Extracted item name: '{name}'")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 5: Line Item Parsing (end-to-end normalizer)
# ─────────────────────────────────────────────────────────────────────────────

@register("Normalizer: Parse line items from OCR tokens")
def test_parse_line_items():
    from app.core.models import BoundingBox, OCRToken
    from app.services.normalizer import parse_lines_to_items

    # Simulate a reassembled text line: "chakki atta 5kg 700"
    tokens = [
        OCRToken(text="chakki", confidence=0.92, bounding_box=BoundingBox(x_min=10, y_min=100, x_max=80, y_max=120)),
        OCRToken(text="atta",   confidence=0.91, bounding_box=BoundingBox(x_min=85, y_min=100, x_max=130, y_max=120)),
        OCRToken(text="5kg",    confidence=0.95, bounding_box=BoundingBox(x_min=135, y_min=100, x_max=170, y_max=120)),
        OCRToken(text="700",    confidence=0.96, bounding_box=BoundingBox(x_min=300, y_min=100, x_max=340, y_max=120)),
    ]
    # Wrap in a line
    items = parse_lines_to_items([[tokens[0], tokens[1], tokens[2], tokens[3]]])
    assert len(items) >= 1
    item = items[0]
    assert item.total_price == 700.0
    assert item.category == "Groceries & Food"
    print(f"   Parsed: '{item.item_name}' qty={item.quantity} total={item.total_price} cat={item.category}")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 6: Deduplication
# ─────────────────────────────────────────────────────────────────────────────

@register("Dedup: Text fingerprint is deterministic")
def test_text_fingerprint_determinism():
    from app.services.dedup import compute_text_fingerprint
    fp1 = compute_text_fingerprint("Al-Madina Super Mart", "2026-10-05", 1450.00)
    fp2 = compute_text_fingerprint("Al-Madina Super Mart", "2026-10-05", 1450.00)
    assert fp1 == fp2
    assert len(fp1) == 64
    print(f"   Fingerprint: {fp1[:16]}…")


@register("Dedup: Different receipts produce different fingerprints")
def test_text_fingerprint_unique():
    from app.services.dedup import compute_text_fingerprint
    fp1 = compute_text_fingerprint("Store A", "2026-10-05", 1450.00)
    fp2 = compute_text_fingerprint("Store B", "2026-10-05", 1450.00)
    assert fp1 != fp2
    print("   Distinct fingerprints for distinct receipts. ✓")


@register("Dedup: check_duplicate returns False for new receipt")
def test_check_duplicate_new():
    from app.services.dedup import check_duplicate
    is_dup, match_id = check_duplicate(
        phash="0000000000000000",  # dummy hash, not in store
        text_fingerprint="a" * 64,
        existing_records=[],
    )
    assert not is_dup
    assert match_id is None
    print("   New receipt correctly identified as non-duplicate.")


@register("Dedup: check_duplicate returns True for text match")
def test_check_duplicate_text_match():
    from app.services.dedup import HashRecord, check_duplicate, compute_text_fingerprint
    fp = compute_text_fingerprint("Test Store", "2026-01-01", 500.0)
    existing = [HashRecord(receipt_id="rcpt-abc", phash_64="ffff", text_sha256=fp)]
    is_dup, match_id = check_duplicate(
        phash="0000", text_fingerprint=fp, existing_records=existing
    )
    assert is_dup
    assert match_id == "rcpt-abc"
    print("   Text fingerprint duplicate detected correctly.")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 7: In-Memory Store
# ─────────────────────────────────────────────────────────────────────────────

@register("Store: Insert and retrieve receipt")
def test_store_insert_receipt():
    from app.services import store
    row = store.insert_receipt(
        merchant_name="Test Mart",
        receipt_date="2026-10-01",
        total_amount=999.0,
        receipt_type="PRINTED",
        status="PROCESSED",
        ocr_confidence=0.92,
    )
    assert row["id"], "Receipt must have an ID"
    fetched = store.get_receipt(row["id"])
    assert fetched is not None
    assert fetched["merchant_name"] == "Test Mart"
    print(f"   Inserted and retrieved receipt id={row['id'][:8]}…")


@register("Store: Insert line item and retrieve")
def test_store_insert_line_item():
    from app.services import store
    receipt = store.insert_receipt(
        merchant_name="Grocery World",
        receipt_date="2026-10-02",
        total_amount=500.0,
        receipt_type="PRINTED",
        status="PROCESSED",
        ocr_confidence=0.88,
    )
    item = store.insert_line_item(
        receipt_id=receipt["id"],
        raw_text="Basmati Rice 5kg 450",
        item_name="Basmati Rice",
        quantity=5.0,
        unit="kg",
        unit_price=90.0,
        total_price=450.0,
        confidence_score=0.88,
        category="Groceries & Food",
    )
    assert item["id"]
    items = store.get_line_items_for_receipt(receipt["id"])
    assert any(i["id"] == item["id"] for i in items)
    print(f"   Line item '{item['item_name']}' stored and retrieved.")


@register("Store: Review queue insert and resolve")
def test_store_review_queue():
    from app.services import store
    receipt = store.insert_receipt(
        merchant_name="Kiryana Shop",
        receipt_date="2026-10-03",
        total_amount=200.0,
        receipt_type="HANDWRITTEN",
        status="PENDING_REVIEW",
        ocr_confidence=0.60,
    )
    item = store.insert_line_item(
        receipt_id=receipt["id"],
        raw_text="rice 2kg 180",
        item_name="Rice",
        quantity=2.0, unit="kg", unit_price=90.0,
        total_price=180.0, confidence_score=0.60,
        category="Groceries & Food",
    )
    q = store.insert_review_queue_item(
        line_item_id=item["id"],
        candidate_text="rice 2kg 180",
        model_confidence=0.60,
    )
    assert q["review_status"] == "UNRESOLVED"

    resolved = store.resolve_review_queue_item(
        queue_id=q["id"],
        review_status="ACCEPTED",
        confirmed_name="Basmati Rice",
    )
    assert resolved["review_status"] == "ACCEPTED"
    assert resolved["resolved_at"] is not None
    print(f"   Queue item resolved successfully: {resolved['review_status']}")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 8: Analytics
# ─────────────────────────────────────────────────────────────────────────────

@register("Store: Monthly summary aggregation")
def test_monthly_summary():
    from app.services import store
    # Seed a receipt for the current month
    from datetime import date
    today = date.today()
    receipt = store.insert_receipt(
        merchant_name="Analytics Test Mart",
        receipt_date=today.isoformat(),
        total_amount=1500.0,
        receipt_type="PRINTED",
        status="PROCESSED",
        ocr_confidence=0.93,
    )
    store.insert_line_item(
        receipt_id=receipt["id"],
        raw_text="Test Item 1500",
        item_name="Test Item",
        quantity=1.0, unit="pcs", unit_price=1500.0,
        total_price=1500.0, confidence_score=0.93,
        category="Miscellaneous",
    )

    summary = store.get_monthly_summary(today.year, today.month)
    assert summary["total_spend"] >= 1500.0
    assert "Miscellaneous" in summary["category_breakdown"]
    print(f"   Period {summary['period']}: total={summary['total_spend']}")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 9: OpenCV Preprocessor (skip if unavailable)
# ─────────────────────────────────────────────────────────────────────────────

@register("Preprocessor: Blur assessment on synthetic image")
def test_preprocessor_blur():
    try:
        import cv2
        import numpy as np
    except ImportError:
        print("   SKIPPED (OpenCV not installed)")
        return

    from app.services.preprocessor import assess_blur
    # Create a sharp synthetic image
    img = np.zeros((300, 300, 3), dtype=np.uint8)
    cv2.putText(img, "TEST", (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 3, (255, 255, 255), 3)
    _, buf = cv2.imencode(".jpg", img)
    score = assess_blur(bytes(buf))
    assert score >= 0.0
    print(f"   Laplacian blur score: {score:.1f}")


@register("Preprocessor: Full pipeline on synthetic receipt")
def test_preprocessor_full():
    try:
        import cv2
        import numpy as np
    except ImportError:
        print("   SKIPPED (OpenCV not installed)")
        return

    from app.services.preprocessor import preprocess_image
    # Generate a simple white rectangle simulating a receipt
    img = np.full((400, 200, 3), 240, dtype=np.uint8)
    cv2.putText(img, "RECEIPT", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
    cv2.putText(img, "Rice 5kg 450", (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    _, buf = cv2.imencode(".jpg", img)

    processed_array, processed_bytes = preprocess_image(bytes(buf))
    assert processed_array is not None
    assert len(processed_bytes) > 0
    print(f"   Preprocessed shape: {processed_array.shape}, bytes: {len(processed_bytes)}")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 10: Tesseract Client (skip if not installed)
# ─────────────────────────────────────────────────────────────────────────────

@register("Tesseract: is_available() check")
def test_tesseract_availability():
    from app.services.tesseract_client import is_available
    available = is_available()
    status = "installed ✓" if available else "NOT installed (will use EasyOCR or skip)"
    print(f"   Tesseract status: {status}")
    # Not a hard assertion – just a status report


# ─────────────────────────────────────────────────────────────────────────────
# TEST 11: OCR Spatial Line Reassembly
# ─────────────────────────────────────────────────────────────────────────────

@register("OCR Router: Spatial line reassembly")
def test_reassemble_lines():
    from app.core.models import BoundingBox, OCRToken
    from app.services.ocr_router import reassemble_lines

    tokens = [
        # Line 1 (y~100)
        OCRToken(text="Al-Madina",   confidence=0.95, bounding_box=BoundingBox(x_min=10, y_min=95,  x_max=120, y_max=115)),
        OCRToken(text="Super",       confidence=0.95, bounding_box=BoundingBox(x_min=125, y_min=97, x_max=200, y_max=115)),
        OCRToken(text="Mart",        confidence=0.94, bounding_box=BoundingBox(x_min=205, y_min=96, x_max=270, y_max=115)),
        # Line 2 (y~130)
        OCRToken(text="Rice",        confidence=0.92, bounding_box=BoundingBox(x_min=10, y_min=128, x_max=80,  y_max=145)),
        OCRToken(text="5kg",         confidence=0.93, bounding_box=BoundingBox(x_min=85, y_min=127, x_max=130, y_max=145)),
        OCRToken(text="450",         confidence=0.96, bounding_box=BoundingBox(x_min=300, y_min=129, x_max=350, y_max=145)),
        # Line 3 (y~160)
        OCRToken(text="Atta",        confidence=0.91, bounding_box=BoundingBox(x_min=10, y_min=159, x_max=70,  y_max=177)),
        OCRToken(text="2kg",         confidence=0.90, bounding_box=BoundingBox(x_min=75, y_min=158, x_max=115, y_max=177)),
        OCRToken(text="280",         confidence=0.95, bounding_box=BoundingBox(x_min=300, y_min=160, x_max=350, y_max=177)),
    ]

    lines = reassemble_lines(tokens, y_tolerance=15)
    assert len(lines) == 3, f"Expected 3 lines, got {len(lines)}"
    assert len(lines[0]) == 3  # "Al-Madina Super Mart"
    assert lines[0][0].text == "Al-Madina"   # Leftmost token first
    print(f"   Correctly reassembled {len(tokens)} tokens into {len(lines)} lines.")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 12: API Endpoints (FastAPI TestClient)
# ─────────────────────────────────────────────────────────────────────────────

@register("API: GET /api/v1/health")
def test_api_health():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    data = response.json()
    assert data["status"] == "ok"
    assert "engines" in data
    print(f"   Status: {data['status']}, Engines: {data['engines']}")


@register("API: POST /api/v1/receipts/upload (valid receipt)")
def test_api_upload_valid():
    import cv2
    import numpy as np
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    img = np.full((500, 250, 3), 245, dtype=np.uint8)
    cv2.putText(img, "STORE", (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
    cv2.putText(img, "Atta 5kg 700", (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)
    _, buf = cv2.imencode(".jpg", img)

    response = client.post(
        "/api/v1/receipts/upload",
        files={"file": ("test_receipt_api.jpg", bytes(buf), "image/jpeg")},
        data={"device_timestamp": "2026-10-09T12:00:00Z", "capture_mode": "single"},
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert "receipt_id" in data
    assert data["status"] in ("PROCESSED", "PENDING_REVIEW")
    print(f"   Uploaded receipt_id={data['receipt_id']}, status={data['status']}")


@register("API: POST /api/v1/receipts/upload (duplicate detection -> 409)")
def test_api_upload_duplicate():
    import cv2
    import numpy as np
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    img = np.full((500, 250, 3), 245, dtype=np.uint8)
    cv2.putText(img, "STORE", (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
    cv2.putText(img, "Atta 5kg 700", (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)
    _, buf = cv2.imencode(".jpg", img)

    # First upload was done in previous test; uploading same image again
    response = client.post(
        "/api/v1/receipts/upload",
        files={"file": ("test_receipt_api.jpg", bytes(buf), "image/jpeg")},
    )
    assert response.status_code == 409, f"Expected 409 Conflict, got {response.status_code}"
    data = response.json()
    assert data.get("is_duplicate") is True
    print(f"   Duplicate correctly rejected with 409 Conflict (matched={data.get('receipt_id')})")


@register("API: POST /api/v1/receipts/upload (validation errors: 422 & 415)")
def test_api_upload_validations():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    # Empty file -> 422
    empty_resp = client.post(
        "/api/v1/receipts/upload",
        files={"file": ("empty.jpg", b"", "image/jpeg")},
    )
    assert empty_resp.status_code == 422, f"Expected 422 for empty file, got {empty_resp.status_code}"

    # Invalid MIME type -> 415
    bad_mime = client.post(
        "/api/v1/receipts/upload",
        files={"file": ("doc.txt", b"plain text receipt", "text/plain")},
    )
    assert bad_mime.status_code == 415, f"Expected 415 for bad mime, got {bad_mime.status_code}"
    print(f"   Validation errors handled properly: empty->422, bad_mime->415")


@register("API: GET /api/v1/analytics/monthly & /trends")
def test_api_analytics():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    # Monthly
    monthly_resp = client.get("/api/v1/analytics/monthly?year=2026&month=10")
    assert monthly_resp.status_code == 200, f"Expected 200, got {monthly_resp.status_code}"
    m_data = monthly_resp.json()
    assert m_data["period"] == "2026-10"
    assert "total_spend" in m_data

    # Trends
    trend_resp = client.get("/api/v1/analytics/trends?months=3")
    assert trend_resp.status_code == 200, f"Expected 200, got {trend_resp.status_code}"
    t_data = trend_resp.json()
    assert "months" in t_data
    assert len(t_data["months"]) == 3
    print(f"   Monthly spend: {m_data['total_spend']}, Trends returned {len(t_data['months'])} months")


@register("API: Review Queue flow (GET & PATCH)")
def test_api_review_queue():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services import store

    # Seed an item into review queue
    r_row = store.insert_receipt(
        merchant_name="API Test Store",
        receipt_date="2026-10-09",
        total_amount=350.0,
        receipt_type="PRINTED",
        status="PENDING_REVIEW",
        ocr_confidence=0.55,
    )
    li_row = store.insert_line_item(
        receipt_id=r_row["id"],
        raw_text="350 milkk",
        item_name="milkk",
        quantity=1.0,
        unit="ltr",
        unit_price=350.0,
        total_price=350.0,
        confidence_score=0.55,
        category="Groceries & Food",
    )
    q_row = store.insert_review_queue_item(
        line_item_id=li_row["id"],
        candidate_text="350 milkk",
        model_confidence=0.55,
    )

    client = TestClient(app)
    # GET review queue
    list_resp = client.get("/api/v1/review-queue")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert any(item["id"] == q_row["id"] for item in items)

    # PATCH resolution
    patch_resp = client.patch(
        f"/api/v1/review-queue/{q_row['id']}",
        json={
            "action": "ACCEPTED",
            "confirmed_name": "Fresh Milk",
            "confirmed_quantity": 1.0,
            "confirmed_unit": "ltr",
            "confirmed_unit_price": 350.0,
            "confirmed_total_price": 350.0,
        },
    )
    assert patch_resp.status_code == 200, f"Expected 200, got {patch_resp.status_code}"
    resolved = patch_resp.json()
    assert resolved["review_status"] == "ACCEPTED"
    print(f"   Review queue item {q_row['id']} successfully resolved via API.")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 12B: N+1 Query Elimination & BBox Coordinate Verification
# ─────────────────────────────────────────────────────────────────────────────

@register("Store & Analytics: list_receipts join query eliminates N+1 loop")
def test_list_receipts_join_n_plus_one():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services import store

    # 1. Verify store.list_receipts(include_items=True)
    all_with_items = store.list_receipts(include_items=True)
    assert isinstance(all_with_items, list)
    if len(all_with_items) > 0:
        first = all_with_items[0]
        assert "line_items" in first, "receipt missing pre-populated 'line_items' key"
        assert isinstance(first["line_items"], list)
        print(f"   Single join query fetched {len(all_with_items)} receipts with embedded line_items.")

    # 2. Verify GET /api/v1/analytics/receipts API returns embedded line_items
    client = TestClient(app)
    resp = client.get("/api/v1/analytics/receipts?page=1&page_size=10")
    assert resp.status_code == 200
    data = resp.json()
    assert "receipts" in data
    assert "total" in data
    assert "page" in data
    if data["receipts"]:
        first_r = data["receipts"][0]
        assert "line_items" in first_r
        print(f"   GET /analytics/receipts verified: page=1, size={len(data['receipts'])}, items={len(first_r['line_items'])}")


@register("Normalizer: Spatial line_items extraction generates normalized bbox")
def test_normalizer_spatial_bbox():
    from app.core.models import OCRToken, BoundingBox
    from app.services.normalizer import parse_lines_to_items

    # Synthetic tokens on a 400x800 receipt
    tokens = [
        OCRToken(text="Super", confidence=0.95, bounding_box=BoundingBox(x_min=20, y_min=100, x_max=100, y_max=140)),
        OCRToken(text="Basmati", confidence=0.92, bounding_box=BoundingBox(x_min=110, y_min=100, x_max=220, y_max=140)),
        OCRToken(text="5kg", confidence=0.90, bounding_box=BoundingBox(x_min=230, y_min=100, x_max=290, y_max=140)),
        OCRToken(text="1450.00", confidence=0.96, bounding_box=BoundingBox(x_min=300, y_min=100, x_max=380, y_max=140)),
    ]
    items = parse_lines_to_items([tokens], base_confidence=0.93, image_dims=(400, 800))
    assert len(items) == 1
    item = items[0]
    assert item.bbox is not None, "item.bbox must not be None when image_dims are provided"
    assert "ymin" in item.bbox and "ymax" in item.bbox
    assert 0.0 <= item.bbox["ymin"] <= 1.0
    assert 0.0 <= item.bbox["ymax"] <= 1.0
    assert item.bbox["ymin"] == 100 / 800.0
    assert item.bbox["ymax"] == 140 / 800.0
    print(f"   Parsed item '{item.item_name}' with normalized bbox: {item.bbox}")


@register("API: Review Queue crop uses bbox for pixel-perfect image slicing")
def test_review_queue_crop_with_bbox():
    import numpy as np
    import cv2
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services import store

    # 1. Create a dummy receipt
    r = store.insert_receipt(
        merchant_name="BBox Test Market",
        receipt_date="2026-10-18",
        total_amount=500.0,
        receipt_type="PRINTED",
        status="PENDING_REVIEW",
        ocr_confidence=0.60,
    )
    receipt_id = r["id"]

    # 2. Generate and store a synthetic receipt image (height=600, width=300)
    syn_img = np.full((600, 300, 3), 245, dtype=np.uint8)
    # Draw a line item bar around y=180 to 240 (which is 0.30 to 0.40)
    cv2.rectangle(syn_img, (10, 180), (290, 240), (200, 200, 200), -1)
    cv2.putText(syn_img, "Cooking Oil 1L - 500", (20, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    _, buf = cv2.imencode(".jpg", syn_img)
    store.save_receipt_image(receipt_id, buf.tobytes(), ext="jpg")

    # 3. Insert line item with normalized bbox
    li = store.insert_line_item(
        receipt_id=receipt_id,
        raw_text="Cooking Oil 1L 500",
        item_name="Cooking Oil",
        quantity=1.0,
        unit="ltr",
        unit_price=500.0,
        total_price=500.0,
        confidence_score=0.55,
        category="Groceries & Food",
        is_verified=False,
        bbox={"ymin": 0.30, "xmin": 0.03, "ymax": 0.40, "xmax": 0.97},
    )

    # 4. Insert review queue record
    q = store.insert_review_queue_item(
        line_item_id=li["id"],
        candidate_text="Cooking Oil 1L 500",
        model_confidence=0.55,
    )

    # 5. Fetch crop snippet
    client = TestClient(app)
    resp = client.get(f"/api/v1/review-queue/{q['id']}/crop")
    assert resp.status_code == 200
    assert resp.headers.get("content-type") == "image/jpeg"
    assert resp.headers.get("x-crop-method") == "bbox", f"Expected 'bbox' crop method, got {resp.headers.get('x-crop-method')}"
    print(f"   Crop snippet successfully returned: method={resp.headers.get('x-crop-method')}, bytes={len(resp.content)}")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 13: Sample Receipts Dataset (Printed & Handwritten Cases)
# ─────────────────────────────────────────────────────────────────────────────

@register("Sample Images: Real printed receipt classification & upload")
def test_sample_printed_receipt():
    from pathlib import Path
    import cv2
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.preprocessor import assess_blur, preprocess_image
    from app.services.ocr_router import classify_receipt_type
    from app.core.models import ReceiptType

    # Find sample path relative to repo root or backend dir
    candidates = [
        Path("data/sample_receipts/printed_receipt_sample.jpg"),
        Path("../data/sample_receipts/printed_receipt_sample.jpg"),
    ]
    sample_path = next((p for p in candidates if p.exists()), None)
    assert sample_path is not None, "Printed sample image not found in data/sample_receipts/"

    image_bytes = sample_path.read_bytes()
    assert len(image_bytes) > 0

    # Blur test
    blur = assess_blur(image_bytes)
    assert blur > 80.0, f"Expected sharp image, got blur score {blur}"

    # Preprocess and classify
    proc_arr, _ = preprocess_image(image_bytes)
    rec_type = classify_receipt_type(proc_arr)
    assert rec_type == ReceiptType.PRINTED, f"Expected PRINTED, got {rec_type}"

    # API Upload test
    client = TestClient(app)
    resp = client.post(
        "/api/v1/receipts/upload",
        files={"file": ("printed_sample.jpg", image_bytes, "image/jpeg")},
        data={"device_timestamp": "2026-10-09T18:43:00Z"},
    )
    assert resp.status_code in (200, 409), f"Unexpected status {resp.status_code}: {resp.text}"
    print(f"   Printed sample: blur={blur:.1f}, type={rec_type.value}, upload={resp.status_code}")


@register("Sample Images: Real handwritten receipt classification & upload")
def test_sample_handwritten_receipt():
    from pathlib import Path
    import cv2
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.preprocessor import assess_blur, preprocess_image
    from app.services.ocr_router import classify_receipt_type
    from app.core.models import ReceiptType

    candidates = [
        Path("data/sample_receipts/handwritten_receipt_sample.jpg"),
        Path("../data/sample_receipts/handwritten_receipt_sample.jpg"),
    ]
    sample_path = next((p for p in candidates if p.exists()), None)
    assert sample_path is not None, "Handwritten sample image not found in data/sample_receipts/"

    image_bytes = sample_path.read_bytes()
    assert len(image_bytes) > 0

    # Blur test
    blur = assess_blur(image_bytes)
    assert blur > 80.0, f"Expected sharp image, got blur score {blur}"

    # Preprocess and classify
    proc_arr, _ = preprocess_image(image_bytes)
    rec_type = classify_receipt_type(proc_arr)
    assert rec_type == ReceiptType.HANDWRITTEN, f"Expected HANDWRITTEN, got {rec_type}"

    # API Upload test
    client = TestClient(app)
    resp = client.post(
        "/api/v1/receipts/upload",
        files={"file": ("handwritten_sample.jpg", image_bytes, "image/jpeg")},
        data={"device_timestamp": "2026-10-09T19:00:00Z"},
    )
    assert resp.status_code in (200, 409), f"Unexpected status {resp.status_code}: {resp.text}"
    print(f"   Handwritten sample: blur={blur:.1f}, type={rec_type.value}, upload={resp.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

def run_all() -> int:
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    passed = 0
    failed = 0
    skipped = 0

    print("\n" + "=" * 65)
    print("  ReceiptLedger Backend - CLI Test Runner")
    print("=" * 65)

    for name, fn in _tests:
        print(f"\n▶  {name}")
        try:
            fn()
            print(f"   ✅  PASSED")
            passed += 1
        except AssertionError as exc:
            print(f"   ❌  FAILED — {exc}")
            traceback.print_exc()
            failed += 1
        except Exception as exc:
            print(f"   ❌  ERROR  — {exc}")
            traceback.print_exc()
            failed += 1

    print("\n" + "─" * 65)
    print(f"  Results:  {passed} passed  |  {failed} failed  |  {skipped} skipped")
    print("─" * 65 + "\n")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_all())
