"""
ReceiptLedger – Gemini vs Local Pipeline A/B Test
==================================================
Runs BOTH the local OCR pipeline (Tesseract + fuzzy matching) AND the Gemini
vision path on the same receipt image, then prints a side-by-side comparison.

Usage:
    cd backend
    .venv\\Scripts\\python test_gemini_vs_local.py [image_path]

    # Example – test METRO receipt:
    .venv\\Scripts\\python test_gemini_vs_local.py ..\data\sample_receipts\metro_safari_park_sample.png

    # Without argument, tests both sample receipts sequentially.

Outputs:
    - Side-by-side table of items extracted by each engine
    - Confidence scores
    - Category assignments
    - Summary metrics: item count, total amount match, avg confidence, review flags
"""

import sys
import os
import time
import asyncio
import logging
from pathlib import Path
from typing import List, Optional

# Force utf-8 encoding on Windows console
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Path setup (run from backend/ directory) ─────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
os.chdir(Path(__file__).parent)

from dotenv import load_dotenv
load_dotenv(".env")

logging.basicConfig(level=logging.WARNING)  # Suppress verbose pipeline logs

# ── Now import backend modules ────────────────────────────────────────────────
from app.core.config import settings
from app.core.models import LineItemCreate


def run_local_pipeline(image_bytes: bytes) -> dict:
    """Run Tesseract + regex normalizer + fuzzy match pipeline."""
    import numpy as np
    import cv2
    from app.services.preprocessor import preprocess_image
    from app.services.ocr_router import classify_receipt_type, reassemble_lines
    from app.services.tesseract_client import extract_tokens
    from app.services import normalizer

    t_start = time.perf_counter()

    # Preprocess
    processed_image, processed_bytes = preprocess_image(image_bytes)

    # Classify
    receipt_type = classify_receipt_type(processed_image)

    # OCR with Tesseract
    tokens = extract_tokens(processed_image, lang="eng")

    if not tokens:
        return {"error": "Tesseract returned no tokens", "items": [], "elapsed": 0}

    # Spatial reassembly
    text_lines = reassemble_lines(tokens)

    # NLP normalisation + fuzzy matching
    mean_confidence = sum(t.confidence for t in tokens) / len(tokens)
    line_items = normalizer.parse_lines_to_items(text_lines, base_confidence=mean_confidence)

    elapsed = time.perf_counter() - t_start

    return {
        "engine": "Tesseract 5 + RapidFuzz",
        "receipt_type": receipt_type.value,
        "token_count": len(tokens),
        "items": line_items,
        "mean_ocr_confidence": round(mean_confidence, 3),
        "elapsed": round(elapsed, 2),
    }


def run_gemini_pipeline(image_bytes: bytes) -> dict:
    """Run Gemini 2.0 Flash vision path."""
    from app.services.gemini_client import extract_and_parse, is_available

    if not is_available():
        return {
            "error": (
                "GEMINI_API_KEY not set in backend/.env\n"
                "  1. Go to https://aistudio.google.com/app/apikey\n"
                "  2. Create a key and paste it as: GEMINI_API_KEY=<your_key>"
            ),
            "items": [],
            "elapsed": 0,
        }

    t_start = time.perf_counter()

    # Detect mime type
    mime = "image/jpeg"
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        mime = "image/png"

    line_items, metadata = extract_and_parse(image_bytes, mime_type=mime)
    elapsed = time.perf_counter() - t_start

    return {
        "engine": f"Gemini ({metadata.get('_model_used', settings.gemini_model) if metadata else settings.gemini_model})",
        "merchant_name": metadata.get("merchant_name") if metadata else None,
        "receipt_date": metadata.get("receipt_date") if metadata else None,
        "total_amount": metadata.get("total_amount") if metadata else None,
        "ocr_quality": metadata.get("ocr_quality") if metadata else None,
        "notes": metadata.get("notes") if metadata else None,
        "items": line_items,
        "elapsed": round(elapsed, 2),
    }


def print_results(image_path: str, local: dict, gemini: dict):
    width = 120
    print("\n" + "=" * width)
    print(f"  IMAGE: {image_path}")
    print("=" * width)

    # ── Local pipeline results ──────────────────────────────────────────────
    print(f"\n{'-'*width}")
    print(f"  LOCAL PIPELINE  ({local.get('engine', 'N/A')})  |  "
          f"Time: {local.get('elapsed', 0):.2f}s  |  "
          f"Tokens: {local.get('token_count', 0)}  |  "
          f"Mean OCR conf: {local.get('mean_ocr_confidence', 0):.3f}  |  "
          f"Type: {local.get('receipt_type', '?')}")
    print(f"{'-'*width}")

    if local.get("error"):
        print(f"  ERROR: {local['error']}")
    else:
        local_items: List[LineItemCreate] = local.get("items", [])
        print(f"  {'Item Name':<35} {'Qty':>6} {'Unit':<5} {'Unit Price':>12} {'Total':>10} {'Cat':<22} {'Conf':>6} {'Review'}")
        print(f"  {'-'*35} {'-'*6} {'-'*5} {'-'*12} {'-'*10} {'-'*22} {'-'*6} {'-'*6}")
        for li in local_items:
            needs_review = li.confidence_score < settings.review_confidence_threshold
            print(f"  {li.item_name:<35} {li.quantity:>6.2f} {li.unit:<5} "
                  f"{li.unit_price:>12.2f} {li.total_price:>10.2f} "
                  f"{li.category:<22} {li.confidence_score:>6.3f} "
                  f"{'[REVIEW]' if needs_review else 'OK'}")

        total_local = sum(li.total_price for li in local_items)
        review_count = sum(1 for li in local_items if li.confidence_score < settings.review_confidence_threshold)
        misc_count = sum(1 for li in local_items if li.category == "Miscellaneous")
        print(f"\n  SUMMARY: {len(local_items)} items  |  "
              f"Items sum: PKR {total_local:,.2f}  |  "
              f"Review flags: {review_count}  |  "
              f"Miscellaneous (unmatched): {misc_count}")

    # ── Gemini pipeline results ─────────────────────────────────────────────
    print(f"\n{'-'*width}")
    print(f"  GEMINI PIPELINE  ({gemini.get('engine', 'N/A')})  |  "
          f"Time: {gemini.get('elapsed', 0):.2f}s  |  "
          f"OCR quality: {gemini.get('ocr_quality', '?')}")
    if gemini.get("merchant_name"):
        print(f"  Merchant: {gemini['merchant_name']}  |  "
              f"Date: {gemini.get('receipt_date')}  |  "
              f"Total: PKR {gemini.get('total_amount')}")
    if gemini.get("notes"):
        print(f"  Notes: {gemini['notes']}")
    print(f"{'-'*width}")

    if gemini.get("error"):
        print(f"  ERROR: {gemini['error']}")
    else:
        gemini_items: List[LineItemCreate] = gemini.get("items", [])
        print(f"  {'Item Name':<35} {'Qty':>6} {'Unit':<5} {'Unit Price':>12} {'Total':>10} {'Cat':<22} {'Conf':>6} {'Review'}")
        print(f"  {'-'*35} {'-'*6} {'-'*5} {'-'*12} {'-'*10} {'-'*22} {'-'*6} {'-'*6}")
        for li in gemini_items:
            needs_review = li.confidence_score < settings.review_confidence_threshold
            print(f"  {li.item_name:<35} {li.quantity:>6.2f} {li.unit:<5} "
                  f"{li.unit_price:>12.2f} {li.total_price:>10.2f} "
                  f"{li.category:<22} {li.confidence_score:>6.3f} "
                  f"{'[REVIEW]' if needs_review else 'OK'}")

        total_gemini = sum(li.total_price for li in gemini_items)
        review_count_g = sum(1 for li in gemini_items if li.confidence_score < settings.review_confidence_threshold)
        misc_count_g = sum(1 for li in gemini_items if li.category == "Miscellaneous")
        print(f"\n  SUMMARY: {len(gemini_items)} items  |  "
              f"Items sum: PKR {total_gemini:,.2f}  |  "
              f"Review flags: {review_count_g}  |  "
              f"Miscellaneous (unmatched): {misc_count_g}")

    # ── Head-to-head comparison ─────────────────────────────────────────────
    if not local.get("error") and not gemini.get("error"):
        local_items = local.get("items", [])
        gemini_items = gemini.get("items", [])
        print(f"\n{'-'*width}")
        print("  HEAD-TO-HEAD COMPARISON")
        print(f"{'-'*width}")
        l_count = len(local_items)
        g_count = len(gemini_items)
        l_avg_conf = (sum(li.confidence_score for li in local_items) / l_count) if l_count else 0
        g_avg_conf = (sum(li.confidence_score for li in gemini_items) / g_count) if g_count else 0
        l_misc = sum(1 for li in local_items if li.category == "Miscellaneous")
        g_misc = sum(1 for li in gemini_items if li.category == "Miscellaneous")

        print(f"  {'Metric':<35} {'Local':>20} {'Gemini':>20}")
        print(f"  {'-'*35} {'-'*20} {'-'*20}")
        print(f"  {'Items extracted':<35} {l_count:>20} {g_count:>20}")
        print(f"  {'Avg confidence score':<35} {l_avg_conf:>20.3f} {g_avg_conf:>20.3f}")
        print(f"  {'Miscellaneous (uncategorized)':<35} {l_misc:>20} {g_misc:>20}")
        l_total = sum(li.total_price for li in local_items)
        g_total = sum(li.total_price for li in gemini_items)
        print(f"  {'Items sum (PKR)':<35} {l_total:>20,.2f} {g_total:>20,.2f}")
        if gemini.get("total_amount"):
            print(f"  {'Gemini stated grand total (PKR)':<35} {'N/A':>20} {gemini['total_amount']:>20,.2f}")
        print(f"  {'Processing time (s)':<35} {local['elapsed']:>20.2f} {gemini['elapsed']:>20.2f}")

    print("=" * width + "\n")


def test_image(image_path: str):
    path = Path(image_path)
    if not path.exists():
        print(f"[ERROR] File not found: {image_path}")
        return

    image_bytes = path.read_bytes()
    print(f"\n[INFO] Testing: {path.name}  ({len(image_bytes) / 1024:.1f} KB)")

    print("[INFO] Running local pipeline...")
    local_result = run_local_pipeline(image_bytes)

    print("[INFO] Running Gemini pipeline...")
    gemini_result = run_gemini_pipeline(image_bytes)

    print_results(str(path), local_result, gemini_result)


if __name__ == "__main__":
    sample_dir = Path("..") / "data" / "sample_receipts"

    if len(sys.argv) > 1:
        test_image(sys.argv[1])
    else:
        # Test all images in sample_receipts/
        images = list(sample_dir.glob("*.png")) + list(sample_dir.glob("*.jpg"))
        if not images:
            print(f"[ERROR] No images found in {sample_dir}")
            print("Usage: python test_gemini_vs_local.py <path_to_receipt_image>")
            sys.exit(1)

        for img in sorted(images):
            test_image(str(img))
