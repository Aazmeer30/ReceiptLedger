"""
ReceiptLedger – Pydantic Data Models (Schemas)
=================================================
All request/response schemas and shared domain types used across the API
and service layers are defined here for a single source of truth.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ── Enumerations ──────────────────────────────────────────────────────────────

class ReceiptType(str, Enum):
    PRINTED = "PRINTED"
    HANDWRITTEN = "HANDWRITTEN"


class ReceiptStatus(str, Enum):
    PROCESSED = "PROCESSED"
    PENDING_REVIEW = "PENDING_REVIEW"
    DUPLICATE = "DUPLICATE"


class ReviewStatus(str, Enum):
    UNRESOLVED = "UNRESOLVED"
    ACCEPTED = "ACCEPTED"
    EDITED = "EDITED"


class CaptureMode(str, Enum):
    SINGLE = "single"
    BATCH = "batch"


# ── Category ──────────────────────────────────────────────────────────────────

SEEDED_CATEGORIES: List[Dict[str, str]] = [
    {"name": "Groceries & Food",      "color_hex": "#10B981",
     "description": "Staples, dairy, flour, produce, and fresh meat"},
    {"name": "Household & Cleaning",  "color_hex": "#3B82F6",
     "description": "Detergents, cleaning supplies, and paper goods"},
    {"name": "Personal Care",         "color_hex": "#8B5CF6",
     "description": "Toiletries, skincare, and hygiene essentials"},
    {"name": "Utilities & Bills",     "color_hex": "#F59E0B",
     "description": "Electricity, gas, water, and top-up bills"},
    {"name": "Snacks & Beverages",    "color_hex": "#EC4899",
     "description": "Confectionery, soft drinks, tea, and bakeries"},
    {"name": "Miscellaneous",         "color_hex": "#6B7280",
     "description": "Unclassified or irregular expenses"},
]


# ── OCR Token (internal pipeline object) ─────────────────────────────────────

class BoundingBox(BaseModel):
    x_min: int
    y_min: int
    x_max: int
    y_max: int

    def __init__(self, x_min: Optional[int] = None, y_min: Optional[int] = None, x_max: Optional[int] = None, y_max: Optional[int] = None, **data):
        if x_min is not None and "x_min" not in data:
            data["x_min"] = x_min
        if y_min is not None and "y_min" not in data:
            data["y_min"] = y_min
        if x_max is not None and "x_max" not in data:
            data["x_max"] = x_max
        if y_max is not None and "y_max" not in data:
            data["y_max"] = y_max
        super().__init__(**data)

    @property
    def x_center(self) -> float:
        return (self.x_min + self.x_max) / 2.0

    @property
    def y_center(self) -> float:
        return (self.y_min + self.y_max) / 2.0


class OCRToken(BaseModel):
    """A single word-level token produced by any OCR engine."""
    text: str
    confidence: float = Field(ge=0.0, le=1.0)
    bounding_box: BoundingBox
    line_id: Optional[int] = None


# ── Line Item ─────────────────────────────────────────────────────────────────

class LineItemCreate(BaseModel):
    raw_text: str
    item_name: str
    quantity: float = 1.0
    unit: str = "pcs"
    unit_price: float
    total_price: float
    confidence_score: float = Field(ge=0.0, le=1.0)
    category: str = "Miscellaneous"
    is_verified: bool = False


class LineItemResponse(BaseModel):
    item_id: str
    raw_text: str
    canonical_name: str
    quantity: float
    unit: str
    unit_price: float
    total_price: float
    category: str
    confidence_score: float
    is_verified: bool


# ── Receipt ───────────────────────────────────────────────────────────────────

class UploadReceiptResponse(BaseModel):
    receipt_id: str
    status: ReceiptStatus
    is_duplicate: bool
    merchant_name: Optional[str]
    receipt_date: Optional[str]
    total_amount: float
    confidence_score: float
    needs_review: bool
    receipt_type: ReceiptType
    line_items: List[LineItemResponse]


# ── Analytics ─────────────────────────────────────────────────────────────────

class MonthlySummaryResponse(BaseModel):
    period: str                           # "YYYY-MM"
    total_spend: float
    delta_previous_month: Optional[float]
    receipt_count: int
    category_breakdown: Dict[str, float]  # category_name → total spend


class MonthlyTrendPoint(BaseModel):
    period: str
    total_spend: float
    category_breakdown: Dict[str, float]


class TrendResponse(BaseModel):
    months: List[MonthlyTrendPoint]


# ── Review Queue ──────────────────────────────────────────────────────────────

class ReviewQueueItem(BaseModel):
    queue_id: str
    line_item_id: str
    receipt_id: str
    merchant_name: Optional[str]
    raw_text: str
    candidate_name: str
    model_confidence: float
    review_status: ReviewStatus
    flagged_at: datetime
    resolved_at: Optional[datetime]


class ReviewQueueResolveRequest(BaseModel):
    """Payload for PATCH /api/v1/review-queue/{id}"""
    confirmed_name: str
    confirmed_quantity: Optional[float] = None
    confirmed_unit: Optional[str] = None
    confirmed_unit_price: Optional[float] = None
    confirmed_total_price: Optional[float] = None
    action: ReviewStatus = ReviewStatus.ACCEPTED

    @field_validator("action")
    @classmethod
    def must_be_resolution(cls, v: ReviewStatus) -> ReviewStatus:
        if v == ReviewStatus.UNRESOLVED:
            raise ValueError("action must be ACCEPTED or EDITED, not UNRESOLVED.")
        return v


# ── Health Check ──────────────────────────────────────────────────────────────

class EngineStatus(BaseModel):
    cloud_vision: str
    tesseract: str
    easyocr: str
    gemini: Optional[str] = None
    database: str


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    engines: EngineStatus


# ── Dashboard Groundwork Models ────────────────────────────────────────────────

class DashboardStatCard(BaseModel):
    key: str
    label: str
    value: Any
    formatted_value: str
    change: Optional[float] = None
    change_type: Optional[str] = None  # "increase", "decrease", "neutral"
    helper_text: Optional[str] = None


class CategorySpendDetail(BaseModel):
    category_name: str
    color_hex: str
    description: Optional[str] = None
    total_spend: float
    item_count: int
    percentage_of_total: float


class DashboardOverviewResponse(BaseModel):
    period: str
    year: int
    month: int
    total_spend: float
    delta_previous_month: Optional[float] = None
    delta_percentage: Optional[float] = None
    receipt_count: int
    pending_review_count: int
    verified_items_count: int
    stat_cards: List[DashboardStatCard]
    category_breakdown: List[CategorySpendDetail]
    recent_receipts: List[Dict[str, Any]]


class DashboardReviewSummary(BaseModel):
    total: int
    unresolved: int
    accepted: int
    edited: int


class DashboardSeedResponse(BaseModel):
    status: str
    message: str
    receipts_count: int
    line_items_count: int
    review_items_count: int

