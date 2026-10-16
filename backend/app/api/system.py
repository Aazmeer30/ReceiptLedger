"""
ReceiptLedger – System & Run Observability Endpoints
GET /api/v1/system/runs
GET /api/v1/system/runs/{run_name}
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

from app.core.run_logger import get_run_log, list_run_logs

router = APIRouter(prefix="/system", tags=["System & Observability"])


@router.get(
    "/runs",
    response_model=List[Dict[str, Any]],
    summary="List all recorded evaluation and pipeline runs",
)
async def get_all_runs(
    limit: int = Query(50, ge=1, le=200, description="Max runs to return"),
) -> List[Dict[str, Any]]:
    """
    List historical test runs, benchmark logs, and evaluation reports
    stored under `backend/logs/runs/` with summary metrics.
    """
    return list_run_logs(limit=limit)


@router.get(
    "/runs/{run_identifier}",
    response_model=Dict[str, Any],
    summary="Get detailed run log data by filename or run_id",
)
async def get_run_detail(run_identifier: str) -> Dict[str, Any]:
    """Retrieve full records and metadata for a specific run log."""
    log_data = get_run_log(run_identifier)
    if not log_data:
        raise HTTPException(
            status_code=404,
            detail=f"Run log '{run_identifier}' not found.",
        )
    return log_data
