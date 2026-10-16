r"""
ReceiptLedger – Test All Receipt Images with Google Gemini Vision API
=====================================================================
Discovers all receipt images across data/sample_receipts and data/real_web_receipts (33 total),
submits each to Gemini Vision API, validates structured outputs, tracks latency & accuracy,
and outputs comprehensive JSON results and formatted summary tables.
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
REPO_ROOT = BASE_DIR.parent
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


def find_all_receipt_images() -> List[Path]:
    """Find all receipt images in data/sample_receipts and data/real_web_receipts."""
    dirs_to_check = [
        REPO_ROOT / "data" / "sample_receipts",
        REPO_ROOT / "data" / "real_web_receipts",
    ]
    exts = {".jpg", ".jpeg", ".png", ".webp"}
    images: List[Path] = []
    for d in dirs_to_check:
        if d.exists():
            for p in sorted(d.iterdir()):
                if p.suffix.lower() in exts and p.is_file():
                    images.append(p)
    return images


def test_receipt_with_gemini(image_path: Path, index: int, total_count: int) -> Dict[str, Any]:
    rel_path = image_path.relative_to(REPO_ROOT)
    filesize_kb = round(image_path.stat().st_size / 1024, 1)
    mime = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"

    print(f"\n[{index:02d}/{total_count:02d}] Testing: {rel_path} ({filesize_kb} KB)")

    image_bytes = image_path.read_bytes()
    max_retries = 3
    gemini_data = None
    elapsed = 0.0

    for attempt in range(1, max_retries + 1):
        t0 = time.perf_counter()
        gemini_data = extract_receipt_data(image_bytes, mime_type=mime)
        elapsed = time.perf_counter() - t0
        if gemini_data:
            break
        print(f"     [Retry {attempt}/{max_retries}] Waiting 6s before retry...")
        time.sleep(6.0)

    if not gemini_data:
        print(f"     [-] Gemini Failed after {max_retries} attempts ({elapsed:.2f}s)")
        return {
            "index": index,
            "filename": image_path.name,
            "relative_path": str(rel_path),
            "filesize_kb": filesize_kb,
            "success": False,
            "elapsed": round(elapsed, 2),
            "error": "Failed to extract structured data",
        }

    items = gemini_result_to_line_items(gemini_data)
    merchant = gemini_data.get("merchant_name") or "Unknown"
    date = gemini_data.get("receipt_date") or "N/A"
    currency = gemini_data.get("currency") or "PKR"
    stated_total = gemini_data.get("total_amount")
    ocr_quality = gemini_data.get("ocr_quality") or "N/A"
    model_used = gemini_data.get("_model_used", settings.gemini_model)
    items_sum = round(sum(it.total_price for it in items), 2)

    total_diff = None
    if stated_total is not None and stated_total > 0:
        total_diff = round(abs(stated_total - items_sum), 2)

    print(f"     [+] Success ({elapsed:.2f}s) | Model: {model_used} | Quality: {ocr_quality}")
    print(f"         Merchant: {merchant} | Date: {date} | Stated: {currency} {stated_total} | Items Sum: {currency} {items_sum} | Diff: {total_diff}")
    print(f"         Extracted {len(items)} items:")
    for it in items[:4]:
        print(f"           - {it.item_name:<32} {it.quantity:>5} {it.unit:<4} @ {currency} {it.unit_price:>8.2f} = {currency} {it.total_price:>8.2f} [{it.category}] (conf={it.confidence_score:.2f})")
    if len(items) > 4:
        print(f"           ... and {len(items) - 4} more items")

    return {
        "index": index,
        "filename": image_path.name,
        "relative_path": str(rel_path),
        "filesize_kb": filesize_kb,
        "success": True,
        "model_used": model_used,
        "elapsed": round(elapsed, 2),
        "merchant_name": merchant,
        "receipt_date": date,
        "currency": currency,
        "stated_total": stated_total,
        "items_sum": items_sum,
        "total_diff": total_diff,
        "ocr_quality": ocr_quality,
        "notes": gemini_data.get("notes"),
        "items_count": len(items),
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
            for it in items
        ],
    }


def main():
    print("=" * 110)
    print("  RECEIPTLEDGER - COMPLETE GEMINI VISION TEST ON ALL PRESENT IMAGES")
    print(f"  Gemini API Key configured: {'YES' if is_available() else 'NO'}")
    print(f"  Default Gemini Model: {settings.gemini_model}")
    print("=" * 110)

    if not is_available():
        print("[ERROR] GEMINI_API_KEY is not set in backend/.env. Aborting.")
        sys.exit(1)

    images = find_all_receipt_images()
    print(f"Found {len(images)} receipt images across sample_receipts and real_web_receipts directories.")
    if not images:
        print("[ERROR] No receipt images found.")
        sys.exit(1)

    results = []
    t_start_all = time.perf_counter()

    for idx, img_path in enumerate(images, 1):
        res = test_receipt_with_gemini(img_path, idx, len(images))
        results.append(res)
        # 3.5 second pause between calls to strictly avoid free-tier 15 RPM throttling
        if idx < len(images):
            time.sleep(3.5)

    total_duration = time.perf_counter() - t_start_all

    # ─────────────────────────────────────────────────────────────────────────
    # Summary Table
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 125)
    print(f"  ALL {len(images)} IMAGES - GEMINI VISION EVALUATION SUMMARY")
    print("=" * 125)
    header = f"  {'#':<3} {'Image Name':<34} {'Status':<8} {'Merchant':<25} {'Date':<11} {'Items':>6} {'Stated Total':>14} {'Items Sum':>14} {'Time':>7}"
    print(header)
    print("  " + "-" * 123)

    success_count = sum(1 for r in results if r.get("success"))
    total_items = sum(r.get("items_count", 0) for r in results if r.get("success"))
    avg_latency = (
        sum(r.get("elapsed", 0) for r in results if r.get("success")) / success_count
        if success_count > 0
        else 0
    )

    for r in results:
        idx_str = f"{r.get('index', 0):<3}"
        name = (r.get("filename") or "")[:33]
        status = "PASS" if r.get("success") else "FAIL"
        merchant = (r.get("merchant_name") or "N/A")[:24]
        date = (r.get("receipt_date") or "N/A")[:10]
        items_cnt = r.get("items_count", 0)
        curr = r.get("currency", "PKR")

        stated = (
            f"{curr} {r.get('stated_total'):,.2f}"
            if r.get("stated_total") is not None
            else "N/A"
        )
        isum = (
            f"{curr} {r.get('items_sum'):,.2f}"
            if r.get("items_sum") is not None
            else "N/A"
        )
        elapsed_str = f"{r.get('elapsed', 0):.2f}s"

        print(f"  {idx_str} {name:<34} {status:<8} {merchant:<25} {date:<11} {items_cnt:>6} {stated:>14} {isum:>14} {elapsed_str:>7}")

    print("  " + "-" * 123)
    print(f"  TOTALS: {success_count}/{len(images)} Successful ({success_count/len(images)*100:.1f}%) | "
          f"Total Line Items Extracted: {total_items} | "
          f"Avg Latency: {avg_latency:.2f}s | Total Test Duration: {total_duration:.1f}s")
    print("=" * 125)

    # ── Save Observability Run Log ───────────────────────────────────────────
    metrics = {
        "total_receipts": len(images),
        "success_count": success_count,
        "failure_count": len(images) - success_count,
        "success_rate_percent": round(success_count / len(images) * 100, 1),
        "total_items_extracted": total_items,
        "average_latency_seconds": round(avg_latency, 2),
        "total_duration_seconds": round(total_duration, 1),
    }
    metadata = {
        "model": settings.gemini_model,
        "evaluation_suite": "complete_33_receipt_dataset",
        "dataset_directories": [
            "data/sample_receipts",
            "data/real_web_receipts",
        ],
    }

    log_path = save_run_log(
        descriptor="gemini_all_images_eval",
        records=results,
        metrics=metrics,
        metadata=metadata,
    )
    print(f"\n[OBSERVABILITY] Timestamped run log saved to:\n  -> {log_path.resolve()}")

    # Also maintain latest pointer at BASE_DIR / "gemini_all_images_eval.json"
    out_file = BASE_DIR / "gemini_all_images_eval.json"
    out_file.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[INFO] Latest results JSON updated at:\n  -> {out_file.resolve()}")


if __name__ == "__main__":
    main()
