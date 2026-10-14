"""
ReceiptLedger – In-Memory Data Store
======================================
When Supabase is not configured (e.g., local dev / CLI testing), this module
acts as the persistence layer, providing all the same query operations against
in-memory Python dicts.  The interface mirrors what the Supabase client would
provide, making it trivial to swap in the real DB later.

Tables (as Python dicts keyed by UUID str):
  - receipts
  - line_items
  - review_queue
  - categories  (pre-seeded at module load)

All UUIDs are generated via Python's `uuid` module.
"""

from __future__ import annotations

import uuid
from datetime import datetime, date
from typing import Any, Dict, List, Optional

from app.core.models import SEEDED_CATEGORIES


# ── In-Memory Tables ──────────────────────────────────────────────────────────

_categories: Dict[str, Dict] = {}
_receipts: Dict[str, Dict] = {}
_line_items: Dict[str, Dict] = {}
_review_queue: Dict[str, Dict] = {}


def _seed_categories() -> None:
    """Pre-populate the categories table with baseline category definitions."""
    for cat in SEEDED_CATEGORIES:
        cat_id = str(uuid.uuid4())
        _categories[cat_id] = {
            "id": cat_id,
            "name": cat["name"],
            "color_hex": cat["color_hex"],
            "description": cat["description"],
        }


_seed_categories()


# ── Category Helpers ──────────────────────────────────────────────────────────

def get_category_id(name: str) -> Optional[str]:
    """Return the category UUID for a given category name, or None if not found."""
    for cat_id, cat in _categories.items():
        if cat["name"] == name:
            return cat_id
    return None


def get_all_categories() -> List[Dict]:
    return list(_categories.values())


# ── Receipt Operations ────────────────────────────────────────────────────────

def insert_receipt(
    merchant_name: Optional[str],
    receipt_date: Optional[str],
    total_amount: float,
    receipt_type: str,
    status: str,
    ocr_confidence: float,
    user_id: Optional[str] = None,
) -> Dict:
    receipt_id = str(uuid.uuid4())
    row = {
        "id": receipt_id,
        "user_id": user_id or "anonymous",
        "merchant_name": merchant_name,
        "receipt_date": receipt_date or date.today().isoformat(),
        "total_amount": total_amount,
        "receipt_type": receipt_type,
        "status": status,
        "ocr_confidence": ocr_confidence,
        "created_at": datetime.utcnow().isoformat(),
    }
    _receipts[receipt_id] = row
    return row


def get_receipt(receipt_id: str) -> Optional[Dict]:
    return _receipts.get(receipt_id)


def list_receipts(user_id: Optional[str] = None) -> List[Dict]:
    rows = list(_receipts.values())
    if user_id:
        rows = [r for r in rows if r.get("user_id") == user_id]
    return sorted(rows, key=lambda r: r["created_at"], reverse=True)


# ── Line Item Operations ──────────────────────────────────────────────────────

def insert_line_item(
    receipt_id: str,
    raw_text: str,
    item_name: str,
    quantity: float,
    unit: str,
    unit_price: float,
    total_price: float,
    confidence_score: float,
    category: str,
    is_verified: bool = False,
) -> Dict:
    item_id = str(uuid.uuid4())
    cat_id = get_category_id(category) or get_category_id("Miscellaneous")
    row = {
        "id": item_id,
        "receipt_id": receipt_id,
        "category_id": cat_id,
        "category_name": category,
        "raw_text": raw_text,
        "item_name": item_name,
        "quantity": quantity,
        "unit": unit,
        "unit_price": unit_price,
        "total_price": total_price,
        "confidence_score": confidence_score,
        "is_verified": is_verified,
    }
    _line_items[item_id] = row
    return row


def get_line_items_for_receipt(receipt_id: str) -> List[Dict]:
    return [li for li in _line_items.values() if li["receipt_id"] == receipt_id]


def update_line_item(item_id: str, updates: Dict[str, Any]) -> Optional[Dict]:
    if item_id not in _line_items:
        return None
    _line_items[item_id].update(updates)
    return _line_items[item_id]


# ── Review Queue Operations ───────────────────────────────────────────────────

def insert_review_queue_item(
    line_item_id: str,
    candidate_text: str,
    model_confidence: float,
) -> Dict:
    queue_id = str(uuid.uuid4())
    row = {
        "id": queue_id,
        "line_item_id": line_item_id,
        "candidate_text": candidate_text,
        "model_confidence": model_confidence,
        "review_status": "UNRESOLVED",
        "flagged_at": datetime.utcnow().isoformat(),
        "resolved_at": None,
    }
    _review_queue[queue_id] = row
    return row


def get_review_queue(status: str = "UNRESOLVED") -> List[Dict]:
    """Return review queue items, enriched with receipt/line_item data."""
    results = []
    for q in _review_queue.values():
        if q["review_status"] != status and status != "ALL":
            continue
        # Enrich with line item data
        li = _line_items.get(q["line_item_id"], {})
        receipt = _receipts.get(li.get("receipt_id", ""), {})
        results.append({
            **q,
            "line_item": li,
            "receipt_id": li.get("receipt_id"),
            "merchant_name": receipt.get("merchant_name"),
        })
    return sorted(results, key=lambda r: r["flagged_at"], reverse=True)


def resolve_review_queue_item(
    queue_id: str,
    review_status: str,
    confirmed_name: Optional[str] = None,
    confirmed_quantity: Optional[float] = None,
    confirmed_unit: Optional[str] = None,
    confirmed_unit_price: Optional[float] = None,
    confirmed_total_price: Optional[float] = None,
) -> Optional[Dict]:
    if queue_id not in _review_queue:
        return None

    # Update queue record
    _review_queue[queue_id]["review_status"] = review_status
    _review_queue[queue_id]["resolved_at"] = datetime.utcnow().isoformat()

    # Update the underlying line item with confirmed values
    line_item_id = _review_queue[queue_id]["line_item_id"]
    updates: Dict[str, Any] = {"is_verified": True}
    if confirmed_name:
        updates["item_name"] = confirmed_name
    if confirmed_quantity is not None:
        updates["quantity"] = confirmed_quantity
    if confirmed_unit:
        updates["unit"] = confirmed_unit
    if confirmed_unit_price is not None:
        updates["unit_price"] = confirmed_unit_price
    if confirmed_total_price is not None:
        updates["total_price"] = confirmed_total_price

    update_line_item(line_item_id, updates)
    return _review_queue[queue_id]


# ── Analytics Queries ─────────────────────────────────────────────────────────

def get_monthly_summary(year: int, month: int) -> Dict:
    """
    Aggregate spend data for the given year/month.
    Returns category_breakdown, total_spend, receipt_count.
    """
    period = f"{year:04d}-{month:02d}"
    period_receipts = [
        r for r in _receipts.values()
        if r["receipt_date"].startswith(period) and r["status"] != "DUPLICATE"
    ]

    receipt_ids = {r["id"] for r in period_receipts}
    items_in_period = [li for li in _line_items.values() if li["receipt_id"] in receipt_ids]

    total_spend = sum(li["total_price"] for li in items_in_period)
    receipt_count = len(period_receipts)

    # Category breakdown
    category_breakdown: Dict[str, float] = {}
    for li in items_in_period:
        cat = li.get("category_name", "Miscellaneous")
        category_breakdown[cat] = round(category_breakdown.get(cat, 0.0) + li["total_price"], 2)

    return {
        "period": period,
        "total_spend": round(total_spend, 2),
        "receipt_count": receipt_count,
        "category_breakdown": category_breakdown,
    }


def get_monthly_trend(months: int = 3) -> List[Dict]:
    """
    Return per-month totals for the past N months (newest first).
    Useful for the multi-month trend chart.
    """
    from datetime import date, timedelta
    import calendar

    results = []
    today = date.today()

    for i in range(months - 1, -1, -1):
        # Compute target month
        target = today.replace(day=1) - timedelta(days=i * 28)
        # Normalise to first of month
        target = target.replace(day=1)
        summary = get_monthly_summary(target.year, target.month)
        results.append(summary)

    return results


# ── Dashboard Groundwork Helpers ─────────────────────────────────────────────

def get_review_summary() -> Dict[str, int]:
    """Return counts of review queue items by status."""
    total = len(_review_queue)
    unresolved = sum(1 for q in _review_queue.values() if q["review_status"] == "UNRESOLVED")
    accepted = sum(1 for q in _review_queue.values() if q["review_status"] == "ACCEPTED")
    edited = sum(1 for q in _review_queue.values() if q["review_status"] == "EDITED")
    return {
        "total": total,
        "unresolved": unresolved,
        "accepted": accepted,
        "edited": edited,
    }


def get_categories_detailed() -> List[Dict]:
    """Return all categories with aggregated spend and item counts across all receipts."""
    # Compute totals
    cat_spend: Dict[str, float] = {}
    cat_items: Dict[str, int] = {}
    total_all_spend = 0.0

    for li in _line_items.values():
        cname = li.get("category_name", "Miscellaneous")
        price = li.get("total_price", 0.0)
        cat_spend[cname] = cat_spend.get(cname, 0.0) + price
        cat_items[cname] = cat_items.get(cname, 0) + 1
        total_all_spend += price

    results = []
    for cat in SEEDED_CATEGORIES:
        name = cat["name"]
        spend = round(cat_spend.get(name, 0.0), 2)
        count = cat_items.get(name, 0)
        pct = round((spend / total_all_spend * 100.0), 1) if total_all_spend > 0 else 0.0
        results.append({
            "category_name": name,
            "color_hex": cat["color_hex"],
            "description": cat["description"],
            "total_spend": spend,
            "item_count": count,
            "percentage_of_total": pct,
        })
    return results


def get_dashboard_overview(year: Optional[int] = None, month: Optional[int] = None) -> Dict:
    """
    Consolidated single-call overview data for the Web Dashboard.
    Provides key metric cards, category breakdown, trend context, and recent activity.
    """
    today = date.today()
    target_year = year or today.year
    target_month = month or today.month

    current = get_monthly_summary(target_year, target_month)

    # Previous month calculation
    if target_month == 1:
        prev_year, prev_month = target_year - 1, 12
    else:
        prev_year, prev_month = target_year, target_month - 1

    previous = get_monthly_summary(prev_year, prev_month)

    delta = None
    delta_pct = None
    if previous["total_spend"] > 0:
        delta = round(current["total_spend"] - previous["total_spend"], 2)
        delta_pct = round((delta / previous["total_spend"]) * 100.0, 1)

    # Detailed category breakdown for current period
    cat_map = {c["name"]: c for c in SEEDED_CATEGORIES}
    cat_breakdown: List[Dict] = []
    cur_total = current["total_spend"]

    for name, spend in current["category_breakdown"].items():
        meta = cat_map.get(name, {"color_hex": "#6B7280", "description": ""})
        pct = round((spend / cur_total * 100.0), 1) if cur_total > 0 else 0.0
        # Count items for this category in current month
        period_str = f"{target_year:04d}-{target_month:02d}"
        period_rcpt_ids = {
            r["id"] for r in _receipts.values()
            if r["receipt_date"].startswith(period_str) and r["status"] != "DUPLICATE"
        }
        item_count = sum(
            1 for li in _line_items.values()
            if li["receipt_id"] in period_rcpt_ids and li.get("category_name") == name
        )
        cat_breakdown.append({
            "category_name": name,
            "color_hex": meta["color_hex"],
            "description": meta.get("description", ""),
            "total_spend": spend,
            "item_count": item_count,
            "percentage_of_total": pct,
        })

    # Sort categories by spend descending
    cat_breakdown.sort(key=lambda c: c["total_spend"], reverse=True)

    # Review status & verification counts
    rev_summary = get_review_summary()
    verified_items = sum(1 for li in _line_items.values() if li.get("is_verified"))

    # Recent 5 receipts
    recent = list_receipts()[:5]

    # Pre-calculated KPI stat cards for clean frontend card rendering
    stat_cards = [
        {
            "key": "total_spend",
            "label": "Monthly Expenditure",
            "value": current["total_spend"],
            "formatted_value": f"PKR {current['total_spend']:,.2f}",
            "change": delta,
            "change_type": "increase" if delta and delta > 0 else ("decrease" if delta and delta < 0 else "neutral"),
            "helper_text": f"{delta_pct:+.1f}% vs previous month" if delta_pct is not None else "Baseline month",
        },
        {
            "key": "receipt_count",
            "label": "Ingested Receipts",
            "value": current["receipt_count"],
            "formatted_value": str(current["receipt_count"]),
            "change": current["receipt_count"] - previous["receipt_count"],
            "change_type": "increase" if current["receipt_count"] >= previous["receipt_count"] else "decrease",
            "helper_text": f"{previous['receipt_count']} receipts in prior month",
        },
        {
            "key": "pending_reviews",
            "label": "Pending Verification",
            "value": rev_summary["unresolved"],
            "formatted_value": str(rev_summary["unresolved"]),
            "change": None,
            "change_type": "increase" if rev_summary["unresolved"] > 0 else "neutral",
            "helper_text": "Human-in-the-loop review queue items (< 85% confidence)",
        },
        {
            "key": "avg_ticket",
            "label": "Average Receipt Value",
            "value": round(current["total_spend"] / max(current["receipt_count"], 1), 2) if current["receipt_count"] > 0 else 0.0,
            "formatted_value": f"PKR {round(current['total_spend'] / max(current['receipt_count'], 1), 2) if current['receipt_count'] > 0 else 0.0:,.2f}",
            "change": None,
            "change_type": "neutral",
            "helper_text": "Per transaction average",
        },
    ]

    return {
        "period": current["period"],
        "year": target_year,
        "month": target_month,
        "total_spend": current["total_spend"],
        "delta_previous_month": delta,
        "delta_percentage": delta_pct,
        "receipt_count": current["receipt_count"],
        "pending_review_count": rev_summary["unresolved"],
        "verified_items_count": verified_items,
        "stat_cards": stat_cards,
        "category_breakdown": cat_breakdown,
        "recent_receipts": recent,
    }


def seed_demo_data() -> Dict[str, int]:
    """
    Populate realistic demo receipts, line items, and review queue items.
    Allows frontend/dashboard developers to test all views (KPI cards, charts,
    velocity curves, review queue) without manual OCR uploads.
    """
    from datetime import date, timedelta

    today = date.today()
    this_month_str = today.strftime("%Y-%m")
    # Date in previous month
    prev_month_date = today.replace(day=1) - timedelta(days=15)
    prev_month_str = prev_month_date.strftime("%Y-%m")

    # Sample Receipts dataset
    sample_receipts_data = [
        # --- Current Month Receipts ---
        {
            "merchant": "Imtiaz Super Market",
            "date": f"{this_month_str}-04",
            "type": "PRINTED",
            "confidence": 0.94,
            "items": [
                ("Wheat Flour (Chakki Atta) 10kg", 1.0, "bag", 1450.0, 1450.0, 0.95, "Groceries & Food", True),
                ("Olper's Full Cream Milk 1L", 4.0, "ltr", 280.0, 1120.0, 0.93, "Groceries & Food", True),
                ("Surf Excel Detergent Powder 1kg", 1.0, "pkt", 680.0, 680.0, 0.92, "Household & Cleaning", True),
                ("Tapal Danedar Tea 430g", 1.0, "box", 720.0, 720.0, 0.91, "Groceries & Food", True),
            ],
        },
        {
            "merchant": "Chase Up Departmental Store",
            "date": f"{this_month_str}-08",
            "type": "PRINTED",
            "confidence": 0.91,
            "items": [
                ("Dettol Antibacterial Soap 3-Pack", 1.0, "pack", 450.0, 450.0, 0.93, "Personal Care", True),
                ("Lays Wavy Masala Potato Chips", 3.0, "pcs", 100.0, 300.0, 0.90, "Snacks & Beverages", True),
                ("National Tomato Ketchup 500g", 1.0, "bottle", 320.0, 320.0, 0.92, "Groceries & Food", True),
            ],
        },
        {
            "merchant": "Al-Madina Kiryana Store",
            "date": f"{this_month_str}-10",
            "type": "HANDWRITTEN",
            "confidence": 0.78,
            "items": [
                ("Sugar (Cheeni) 2kg", 2.0, "kg", 160.0, 320.0, 0.88, "Groceries & Food", True),
                ("Cooking Oil (Dalda Pouch)", 1.0, "ltr", 530.0, 530.0, 0.72, "Groceries & Food", False),  # Review Queue candidate
                ("Eggs (Anday) 1 Dozen", 1.0, "dozen", 360.0, 360.0, 0.89, "Groceries & Food", True),
            ],
        },
        {
            "merchant": "K-Electric Online Billing",
            "date": f"{this_month_str}-02",
            "type": "PRINTED",
            "confidence": 0.98,
            "items": [
                ("Electricity Bill Consumption", 1.0, "month", 5840.0, 5840.0, 0.98, "Utilities & Bills", True),
            ],
        },
        {
            "merchant": "Bin Hashim Pharmacy & Supermarket",
            "date": f"{this_month_str}-12",
            "type": "PRINTED",
            "confidence": 0.82,
            "items": [
                ("Colgate Total Toothpaste 140g", 1.0, "tube", 310.0, 310.0, 0.91, "Personal Care", True),
                ("Ambiguous Herbal Balm", 1.0, "box", 190.0, 190.0, 0.69, "Personal Care", False),  # Review Queue candidate
            ],
        },
        # --- Previous Month Receipts (for Trends and Delta) ---
        {
            "merchant": "Imtiaz Super Market",
            "date": f"{prev_month_str}-15",
            "type": "PRINTED",
            "confidence": 0.93,
            "items": [
                ("Basmati Rice (Super Kernel) 5kg", 1.0, "bag", 1850.0, 1850.0, 0.94, "Groceries & Food", True),
                ("Ariel Washing Powder 1kg", 1.0, "pkt", 690.0, 690.0, 0.91, "Household & Cleaning", True),
                ("K-Electric Bill Prior Month", 1.0, "month", 6200.0, 6200.0, 0.97, "Utilities & Bills", True),
            ],
        },
        {
            "merchant": "Subhan Milk Shop",
            "date": f"{prev_month_str}-22",
            "type": "HANDWRITTEN",
            "confidence": 0.85,
            "items": [
                ("Fresh Buffalo Milk 5L", 5.0, "ltr", 220.0, 1100.0, 0.87, "Groceries & Food", True),
                ("Plain Yogurt (Dahi) 1kg", 1.0, "kg", 260.0, 260.0, 0.85, "Groceries & Food", True),
            ],
        },
    ]

    receipt_count = 0
    item_count = 0
    review_count = 0

    for r_data in sample_receipts_data:
        total = sum(item[4] for item in r_data["items"])
        status = "PENDING_REVIEW" if any(not item[7] for item in r_data["items"]) else "PROCESSED"
        rcpt = insert_receipt(
            merchant_name=r_data["merchant"],
            receipt_date=r_data["date"],
            total_amount=round(total, 2),
            receipt_type=r_data["type"],
            status=status,
            ocr_confidence=r_data["confidence"],
        )
        receipt_count += 1

        for name, qty, unit, u_price, t_price, conf, cat, verified in r_data["items"]:
            li = insert_line_item(
                receipt_id=rcpt["id"],
                raw_text=name,
                item_name=name,
                quantity=qty,
                unit=unit,
                unit_price=u_price,
                total_price=t_price,
                confidence_score=conf,
                category=cat,
                is_verified=verified,
            )
            item_count += 1

            if not verified:
                insert_review_queue_item(
                    line_item_id=li["id"],
                    candidate_text=name,
                    model_confidence=conf,
                )
                review_count += 1

    return {
        "receipts": receipt_count,
        "line_items": item_count,
        "review_items": review_count,
    }


def reset_store() -> None:
    """Clear all receipts, line items, and review items, re-initializing category definitions."""
    global _receipts, _line_items, _review_queue, _categories
    _receipts.clear()
    _line_items.clear()
    _review_queue.clear()
    _categories.clear()
    _seed_categories()

