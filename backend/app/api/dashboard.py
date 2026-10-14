"""
ReceiptLedger – Web Dashboard Endpoints
=========================================
Groundwork endpoints specifically tailored for the Web Dashboard (React/Vite).

Provides:
  • GET  /api/v1/dashboard/overview        → Consolidated high-level KPIs & spend distributions
  • GET  /api/v1/dashboard/categories      → Category list with hex colors, items count, and total spend
  • GET  /api/v1/dashboard/review-summary  → Human-in-the-loop review status counts (unresolved/accepted/edited)
  • POST /api/v1/dashboard/seed-demo       → Seed realistic Pakistani retail receipts for frontend testing
  • POST /api/v1/dashboard/reset           → Reset in-memory ledger state

References:
  docs/02_SRS.md § 4.1 (FR-6 Spending Analytics Dashboard)
  web/README.md (Dashboard Capabilities & Setup)
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Query, status

from app.core.models import (
    CategorySpendDetail,
    DashboardOverviewResponse,
    DashboardReviewSummary,
    DashboardSeedResponse,
)
from app.services import store

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/dashboard/overview",
    response_model=DashboardOverviewResponse,
    summary="Consolidated dashboard overview and KPI statistics",
    tags=["Dashboard"],
)
async def get_dashboard_overview(
    year: Optional[int] = Query(
        default=None,
        ge=2020,
        le=2099,
        description="Calendar year (e.g. 2026). Defaults to current year.",
    ),
    month: Optional[int] = Query(
        default=None,
        ge=1,
        le=12,
        description="Calendar month (1-12). Defaults to current month.",
    ),
) -> DashboardOverviewResponse:
    """
    Returns single-call aggregated metrics designed for rapid rendering of the
    Web Dashboard top summary row and main visualization widgets:
      • Ready-to-render KPI Stat Cards (Total Spend, Ingested Receipts, Pending Review items)
      • Monthly comparison (previous month spend delta and percentage change)
      • Category breakdown with UI color tokens and percentages
      • Recent receipt stream for real-time activity feeds
    """
    data = store.get_dashboard_overview(year=year, month=month)
    return DashboardOverviewResponse(**data)


@router.get(
    "/dashboard/categories",
    response_model=List[CategorySpendDetail],
    summary="Category metadata, color mappings, and historical spend totals",
    tags=["Dashboard"],
)
async def get_dashboard_categories() -> List[CategorySpendDetail]:
    """
    Returns all defined spending categories along with their official UI hex colors,
    item counts, and total accumulated expenditure across all receipts.
    Ideal for populating Chart.js donuts and filter legends.
    """
    data = store.get_categories_detailed()
    return [CategorySpendDetail(**c) for c in data]


@router.get(
    "/dashboard/review-summary",
    response_model=DashboardReviewSummary,
    summary="Review Queue status breakdown",
    tags=["Dashboard"],
)
async def get_dashboard_review_summary() -> DashboardReviewSummary:
    """
    Returns counts of unresolved, accepted, and edited review queue items.
    Useful for notification badges and review queue status bars on the dashboard.
    """
    counts = store.get_review_summary()
    return DashboardReviewSummary(**counts)


@router.post(
    "/dashboard/seed-demo",
    response_model=DashboardSeedResponse,
    summary="Populate realistic demo receipts for frontend dashboard testing",
    tags=["Dashboard"],
)
async def seed_dashboard_demo() -> DashboardSeedResponse:
    """
    Utility endpoint for web developers: populates sample printed and handwritten
    receipts (Iman / Web stream) along with candidate items in the review queue
    so charts, velocity curves, and tables can be visually developed without
    needing physical receipt uploads.
    """
    result = store.seed_demo_data()
    logger.info("Demo data seeded: %s", result)
    return DashboardSeedResponse(
        status="success",
        message="Demo receipts, line items, and review queue candidates seeded successfully.",
        receipts_count=result["receipts"],
        line_items_count=result["line_items"],
        review_items_count=result["review_items"],
    )


@router.post(
    "/dashboard/reset",
    summary="Reset in-memory data store",
    tags=["Dashboard"],
)
async def reset_dashboard_data() -> dict:
    """
    Resets the in-memory store to an empty state.
    Allows testing empty/zero states on the dashboard.
    """
    store.reset_store()
    logger.info("In-memory data store was reset.")
    return {"status": "success", "message": "Store reset to clean initial state."}
