"""
ReceiptLedger – Observability & Run Logging System
==================================================
Logs pipeline evaluations, batch benchmarks, and OCR runs to timestamped JSON & LOG
files in a dedicated logs directory (backend/logs/runs/) for auditing, tracking model drift,
and comparing OCR/Gemini performance over time.
"""

from __future__ import annotations

import json
import os
import platform
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Base directory for run logs
BACKEND_DIR = Path(__file__).resolve().parents[2]
LOGS_DIR = BACKEND_DIR / "logs" / "runs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)


def sanitize_descriptor(descriptor: str) -> str:
    """Sanitize descriptor string for safe filename usage."""
    safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in descriptor)
    return safe.strip("_") or "run"


def save_run_log(
    descriptor: str,
    records: List[Dict[str, Any]],
    metrics: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    summary_text: Optional[str] = None,
) -> Path:
    """
    Save a structured run log with timestamp and descriptor.

    Filename format:
        YYYYMMDD_HHMMSS_<descriptor>.json
        YYYYMMDD_HHMMSS_<descriptor>.log (if summary_text provided)

    Args:
        descriptor: Short human-readable identifier (e.g. 'gemini_all_images', 'ocr_benchmark')
        records: List of individual item/receipt result dicts
        metrics: Aggregate metrics (total_count, success_rate, avg_latency, etc.)
        metadata: Model info, pipeline settings, environment info
        summary_text: Optional formatted ASCII / markdown text report to save alongside JSON

    Returns:
        Path to the saved JSON run log file
    """
    now = datetime.now()
    timestamp_prefix = now.strftime("%Y%m%d_%H%M%S")
    safe_desc = sanitize_descriptor(descriptor)
    base_name = f"{timestamp_prefix}_{safe_desc}"

    # Calculate default metrics if not provided
    if metrics is None:
        total = len(records)
        successes = sum(1 for r in records if r.get("success", False))
        metrics = {
            "total_records": total,
            "success_count": successes,
            "failure_count": total - successes,
            "success_rate_percent": round((successes / total * 100), 1) if total > 0 else 0.0,
        }

    run_payload = {
        "run_id": str(uuid.uuid4()),
        "timestamp": now.isoformat(),
        "descriptor": safe_desc,
        "environment": {
            "os": platform.system(),
            "python_version": platform.python_version(),
            "platform_release": platform.release(),
        },
        "metadata": metadata or {},
        "metrics": metrics,
        "records_count": len(records),
        "records": records,
    }

    json_path = LOGS_DIR / f"{base_name}.json"
    json_path.write_text(
        json.dumps(run_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if summary_text:
        log_path = LOGS_DIR / f"{base_name}.log"
        log_path.write_text(summary_text, encoding="utf-8")

    return json_path


def list_run_logs(limit: int = 50) -> List[Dict[str, Any]]:
    """
    List all recorded run logs in reverse chronological order.
    Returns lightweight summary headers without the heavy records array.
    """
    if not LOGS_DIR.exists():
        return []

    json_files = sorted(LOGS_DIR.glob("*.json"), reverse=True)
    summaries = []

    for p in json_files[:limit]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            summaries.append({
                "filename": p.name,
                "filepath": str(p),
                "run_id": data.get("run_id"),
                "timestamp": data.get("timestamp"),
                "descriptor": data.get("descriptor"),
                "metrics": data.get("metrics", {}),
                "metadata": data.get("metadata", {}),
                "records_count": data.get("records_count", 0),
                "size_kb": round(p.stat().st_size / 1024, 1),
            })
        except Exception:
            continue

    return summaries


def get_run_log(filename_or_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve full run log JSON by filename or run_id."""
    if not LOGS_DIR.exists():
        return None

    # Check direct filename
    target = LOGS_DIR / filename_or_id
    if not target.exists() and not filename_or_id.endswith(".json"):
        target = LOGS_DIR / f"{filename_or_id}.json"

    if target.exists() and target.is_file():
        try:
            return json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            return None

    # Search by run_id
    for p in LOGS_DIR.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("run_id") == filename_or_id:
                return data
        except Exception:
            continue

    return None
