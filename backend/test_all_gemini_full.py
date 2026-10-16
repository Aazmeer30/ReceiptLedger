r"""
ReceiptLedger – Full Gemini Vision Evaluation Suite
===================================================
Runs Google Gemini Vision extraction on all sample receipt images,
records structured line items, merchant metadata, confidence scores,
and generates a comprehensive evaluation artifact report.
"""

import os
import sys
import time
import json
from pathlib import Path
from typing import Dict, List, Any, Optional

# Force UTF-8 on Windows console
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure backend root is on sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.chdir(BASE_DIR)

from dotenv import load_dotenv
load_dotenv(".env")

from app.core.config import settings
from app.core.run_logger import save_run_log
from app.services.gemini_client import (
    extract_receipt_data,
    gemini_result_to_line_items,
    is_available,
)
from app.services.preprocessor import preprocess_image
from app.services.ocr_router import classify_receipt_type, reassemble_lines
from app.services.tesseract_client import extract_tokens
from app.services import normalizer


def run_local_pipeline(image_bytes: bytes) -> Dict[str, Any]:
    t_start = time.perf_counter()
    try:
        processed_image, _ = preprocess_image(image_bytes)
        receipt_type = classify_receipt_type(processed_image)
        tokens = extract_tokens(processed_image, lang="eng")
        if not tokens:
            return {"error": "Tesseract returned no tokens", "items": [], "elapsed": 0}
        text_lines = reassemble_lines(tokens)
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
    except Exception as exc:
        return {"error": str(exc), "items": [], "elapsed": round(time.perf_counter() - t_start, 2)}


def test_single_receipt(image_path: Path) -> Dict[str, Any]:
    print(f"\n{'='*100}")
    print(f"  TESTING: {image_path.name}  ({image_path.stat().st_size / 1024:.1f} KB)")
    print(f"{'='*100}")

    image_bytes = image_path.read_bytes()
    mime = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"

    # 1. Run Gemini vision
    print("  -> Calling Gemini Vision API...")
    t_g_start = time.perf_counter()
    gemini_data = extract_receipt_data(image_bytes, mime_type=mime)
    gemini_elapsed = time.perf_counter() - t_g_start

    gemini_items = []
    if gemini_data:
        gemini_items = gemini_result_to_line_items(gemini_data)
        print(f"     [Gemini Success] {len(gemini_items)} items extracted in {gemini_elapsed:.2f}s "
              f"(Model: {gemini_data.get('_model_used', settings.gemini_model)})")
        print(f"     Merchant: {gemini_data.get('merchant_name')} | Date: {gemini_data.get('receipt_date')} | Stated Total: PKR {gemini_data.get('total_amount')}")
    else:
        print(f"     [Gemini Error/Skipped] in {gemini_elapsed:.2f}s")

    # 2. Run Local pipeline for comparison
    print("  -> Running Local Pipeline (Tesseract 5 + RapidFuzz)...")
    local_data = run_local_pipeline(image_bytes)
    local_items = local_data.get("items", [])
    print(f"     [Local Pipeline] {len(local_items)} items extracted in {local_data.get('elapsed', 0):.2f}s "
          f"(OCR Type: {local_data.get('receipt_type', '?')})")

    # Print Gemini Line Items
    if gemini_items:
        print("\n     --- Gemini Extracted Line Items ---")
        print(f"     {'Item Name':<35} {'Qty':>6} {'Unit':<5} {'Unit Price':>10} {'Total':>10} {'Category':<22} {'Conf':>5}")
        print(f"     {'-'*35} {'-'*6} {'-'*5} {'-'*10} {'-'*10} {'-'*22} {'-'*5}")
        for it in gemini_items:
            print(f"     {it.item_name:<35} {it.quantity:>6.2f} {it.unit:<5} {it.unit_price:>10.2f} {it.total_price:>10.2f} {it.category:<22} {it.confidence_score:>5.2f}")
        g_sum = sum(it.total_price for it in gemini_items)
        print(f"     Calculated Items Sum: PKR {g_sum:,.2f}")

    return {
        "filename": image_path.name,
        "filesize_kb": round(image_path.stat().st_size / 1024, 1),
        "gemini": {
            "success": bool(gemini_data),
            "model": gemini_data.get("_model_used", settings.gemini_model) if gemini_data else None,
            "elapsed": round(gemini_elapsed, 2),
            "merchant_name": gemini_data.get("merchant_name") if gemini_data else None,
            "receipt_date": gemini_data.get("receipt_date") if gemini_data else None,
            "stated_total": gemini_data.get("total_amount") if gemini_data else None,
            "currency": gemini_data.get("currency", "PKR") if gemini_data else "PKR",
            "ocr_quality": gemini_data.get("ocr_quality") if gemini_data else None,
            "notes": gemini_data.get("notes") if gemini_data else None,
            "items_count": len(gemini_items),
            "items_sum": round(sum(it.total_price for it in gemini_items), 2),
            "items": [
                {
                    "raw_text": it.raw_text,
                    "item_name": it.item_name,
                    "quantity": it.quantity,
                    "unit": it.unit,
                    "unit_price": it.unit_price,
                    "total_price": it.total_price,
                    "category": it.category,
                    "confidence_score": it.confidence_score,
                }
                for it in gemini_items
            ],
        },
        "local": {
            "elapsed": local_data.get("elapsed", 0),
            "receipt_type": local_data.get("receipt_type", "?"),
            "token_count": local_data.get("token_count", 0),
            "mean_conf": local_data.get("mean_ocr_confidence", 0),
            "items_count": len(local_items),
            "items_sum": round(sum(it.total_price for it in local_items), 2),
            "items": [
                {
                    "item_name": it.item_name,
                    "quantity": it.quantity,
                    "unit": it.unit,
                    "unit_price": it.unit_price,
                    "total_price": it.total_price,
                    "category": it.category,
                    "confidence_score": it.confidence_score,
                }
                for it in local_items
            ],
        },
    }


def main():
    if not is_available():
        print("[ERROR] GEMINI_API_KEY is not set in backend/.env. Cannot run Gemini evaluation.")
        sys.exit(1)

    samples_dir = Path("..") / "data" / "sample_receipts"
    if not samples_dir.exists():
        print(f"[ERROR] Directory not found: {samples_dir}")
        sys.exit(1)

    images = sorted(list(samples_dir.glob("*.png")) + list(samples_dir.glob("*.jpg")) + list(samples_dir.glob("*.jpeg")))
    print(f"\n====================================================================================================")
    print(f"  RECEIPTLEDGER – GEMINI VISION FULL EVALUATION SUITE")
    print(f"  Found {len(images)} sample images in {samples_dir.resolve()}")
    print(f"  Configured Gemini Model: {settings.gemini_model}")
    print(f"====================================================================================================")

    all_results = []
    for idx, img_path in enumerate(images, 1):
        res = test_single_receipt(img_path)
        all_results.append(res)
        # Sleep 2 seconds between API calls to avoid free-tier rate limits (15 RPM)
        if idx < len(images):
            time.sleep(2.0)

    # ── Summary Table ────────────────────────────────────────────────────────
    print(f"\n\n{'='*120}")
    print(f"  OVERALL EVALUATION SUMMARY TABLE ACROSS ALL {len(all_results)} SAMPLE RECEIPTS")
    print(f"{'='*120}")
    print(f"  {'#':<3} {'Receipt Image':<32} {'Merchant':<22} {'Gemini Items':>12} {'Stated Total':>14} {'Items Sum':>12} {'Local Items':>12} {'Time (s)':>9}")
    print(f"  {'-'*3} {'-'*32} {'-'*22} {'-'*12} {'-'*14} {'-'*12} {'-'*12} {'-'*9}")

    total_gemini_items = 0
    total_local_items = 0
    total_gemini_spend = 0.0

    for idx, r in enumerate(all_results, 1):
        g = r["gemini"]
        l = r["local"]
        total_gemini_items += g["items_count"]
        total_local_items += l["items_count"]
        total_gemini_spend += g["items_sum"]

        merchant = (g["merchant_name"] or "Unknown")[:21]
        stated = f"PKR {g['stated_total']:,.2f}" if g["stated_total"] else "N/A"
        g_sum = f"PKR {g['items_sum']:,.2f}"
        print(f"  {idx:<3} {r['filename']:<32} {merchant:<22} {g['items_count']:>12} {stated:>14} {g_sum:>12} {l['items_count']:>12} {g['elapsed']:>8.2f}s")

    print(f"  {'-'*120}")
    print(f"  TOTALS: {total_gemini_items} items extracted across {len(all_results)} receipts | Total Spend: PKR {total_gemini_spend:,.2f} | Local Items: {total_local_items}")

    # ── Save Observability Run Log & JSON Results ─────────────────────────────
    save_run_log(
        descriptor="gemini_vs_local_eval",
        records=all_results,
        metrics={
            "total_receipts": len(all_results),
            "total_gemini_items": total_gemini_items,
            "total_local_items": total_local_items,
            "total_gemini_spend": total_gemini_spend,
        },
        metadata={"model": settings.gemini_model},
    )
    out_json = BASE_DIR / "gemini_eval_results.json"
    out_json.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[INFO] Complete JSON evaluation saved to: {out_json}")


if __name__ == "__main__":
    main()
