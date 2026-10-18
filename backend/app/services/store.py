"""
ReceiptLedger – Data Persistence Store (Supabase + In-Memory Fallback)
=======================================================================
Provides transactional storage operations for:
  • Receipts
  • Line Items
  • Review Queue Items
  • Receipt Deduplication Hashes
  • Spend Categories & Analytics

When Supabase is configured (`settings.supabase_enabled`), all CRUD operations
persist directly to the PostgreSQL database on Supabase.
When Supabase is not configured (e.g. offline dev, isolated test runs), operations
operate against in-memory dictionaries with identical semantics.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.models import SEEDED_CATEGORIES

logger = logging.getLogger(__name__)

# ── In-Memory Tables / Local Cache ────────────────────────────────────────────

_categories: Dict[str, Dict] = {}
_receipts: Dict[str, Dict] = {}
_line_items: Dict[str, Dict] = {}
_review_queue: Dict[str, Dict] = {}
_hashes: Dict[str, Dict] = {}

# Supabase Client Singleton
_supabase_client = None


def _safe_uuid(val: Optional[str]) -> Optional[str]:
    """Ensures a string is a valid UUID, returning None if invalid (e.g. 'anonymous')."""
    if not val:
        return None
    try:
        return str(uuid.UUID(str(val)))
    except (ValueError, AttributeError):
        return None


def get_supabase_client():
    """Lazily initializes and returns the Supabase client if configured."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    if not settings.supabase_enabled:
        return None

    try:
        from supabase import create_client

        # Prefer service role key if available for full server access, else anon key
        key = settings.supabase_service_role_key or settings.supabase_anon_key
        _supabase_client = create_client(settings.supabase_url, key)
        logger.info("Supabase client initialized successfully (%s)", settings.supabase_url)
        return _supabase_client
    except Exception as exc:
        logger.error("Failed to initialize Supabase client: %s", exc)
        return None


def _seed_categories() -> None:
    """Pre-populate local category definitions from SEEDED_CATEGORIES."""
    for cat in SEEDED_CATEGORIES:
        cat_id = str(uuid.uuid4())
        _categories[cat_id] = {
            "id": cat_id,
            "name": cat["name"],
            "color_hex": cat["color_hex"],
            "description": cat["description"],
        }


def _sync_categories() -> None:
    """Sync categories from Supabase if configured, otherwise seed locally."""
    client = get_supabase_client()
    if client:
        try:
            res = client.table("categories").select("*").execute()
            if res.data and len(res.data) > 0:
                _categories.clear()
                for row in res.data:
                    _categories[row["id"]] = {
                        "id": row["id"],
                        "name": row["name"],
                        "color_hex": row.get("color_hex", "#6B7280"),
                        "description": row.get("description", ""),
                    }
                return
        except Exception as exc:
            logger.debug("Initial category sync failed: %s", exc)

    _seed_categories()


# Initialize categories on module load
_sync_categories()


def init_supabase() -> bool:
    """
    Called on backend startup when Supabase is enabled.
    Synchronizes categories from Supabase and preloads deduplication hashes.
    """
    client = get_supabase_client()
    if not client:
        return False

    try:
        # 1. Sync Categories from Supabase
        _sync_categories()
        logger.info("Synced %d categories from Supabase", len(_categories))

        # 2. Preload Hashes into Dedup Engine
        hash_res = client.table("receipt_hashes").select("receipt_id, phash_64, text_fingerprint_sha256").execute()
        if hash_res.data:
            from app.services import dedup
            dedup.load_hashes_from_db(hash_res.data)
            logger.info("Preloaded %d deduplication hashes from Supabase", len(hash_res.data))

        return True
    except Exception as exc:
        logger.warning("Supabase initialization sync encountered issue: %s", exc)
        return False


# ── Category Helpers ──────────────────────────────────────────────────────────

def get_category_id(name: str) -> Optional[str]:
    """Return the category UUID for a given category name, or None if not found."""
    # Exact match (case-insensitive)
    for cat_id, cat in _categories.items():
        if cat["name"].lower() == name.lower():
            return cat_id

    # Substring / partial match
    for cat_id, cat in _categories.items():
        if name.lower() in cat["name"].lower() or cat["name"].lower() in name.lower():
            return cat_id

    # Fallback to Miscellaneous
    for cat_id, cat in _categories.items():
        if "misc" in cat["name"].lower():
            return cat_id

    # Fallback to first available category
    if _categories:
        return list(_categories.keys())[0]

    return None


def get_category_name(cat_id: str) -> str:
    """Return category name for a given UUID, defaulting to 'Miscellaneous'."""
    cat = _categories.get(cat_id)
    return cat["name"] if cat else "Miscellaneous"


def get_all_categories() -> List[Dict]:
    """Return all categories."""
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
    safe_user = _safe_uuid(user_id)
    r_date = receipt_date or date.today().isoformat()

    row = {
        "id": receipt_id,
        "user_id": user_id or "anonymous",
        "merchant_name": merchant_name,
        "receipt_date": r_date,
        "total_amount": float(total_amount),
        "receipt_type": receipt_type,
        "status": status,
        "ocr_confidence": float(ocr_confidence),
        "created_at": datetime.utcnow().isoformat(),
    }
    _receipts[receipt_id] = row

    # Persist to Supabase if enabled
    client = get_supabase_client()
    if client:
        try:
            db_payload = {
                "id": receipt_id,
                "user_id": safe_user,
                "merchant_name": merchant_name,
                "receipt_date": r_date,
                "total_amount": float(total_amount),
                "receipt_type": receipt_type,
                "status": status,
                "ocr_confidence": float(ocr_confidence),
            }
            client.table("receipts").insert(db_payload).execute()
        except Exception as exc:
            logger.warning("Failed to insert receipt to Supabase (%s), stored in-memory", exc)

    return row


def get_receipt(receipt_id: str) -> Optional[Dict]:
    """Fetch single receipt by ID."""
    if receipt_id in _receipts:
        return _receipts[receipt_id]

    client = get_supabase_client()
    if client:
        try:
            res = client.table("receipts").select("*").eq("id", receipt_id).execute()
            if res.data and len(res.data) > 0:
                row = res.data[0]
                _receipts[receipt_id] = row
                return row
        except Exception as exc:
            logger.warning("Supabase get_receipt error: %s", exc)

    return None


def list_receipts(user_id: Optional[str] = None, include_items: bool = False) -> List[Dict]:
    """
    List all receipts ordered by created_at descending.
    When include_items=True, executes a single join query (select("*, line_items(*)"))
    in Supabase or pre-populates line items from local cache, eliminating N+1 queries.
    """
    client = get_supabase_client()
    if client:
        try:
            select_cols = "*, line_items(*)" if include_items else "*"
            q = client.table("receipts").select(select_cols).order("created_at", desc=True)
            safe_user = _safe_uuid(user_id)
            if safe_user:
                q = q.eq("user_id", safe_user)
            res = q.execute()
            if res.data is not None:
                for r in res.data:
                    _receipts[r["id"]] = r
                    if include_items:
                        items = r.get("line_items") or []
                        for li in items:
                            li["category_name"] = get_category_name(li.get("category_id", ""))
                            cached = _line_items.get(li["id"])
                            if cached and "bbox" in cached and not li.get("bbox"):
                                li["bbox"] = cached["bbox"]
                            _line_items[li["id"]] = li
                return res.data
        except Exception as exc:
            logger.warning("Supabase list_receipts query error: %s", exc)

    rows = list(_receipts.values())
    if user_id and user_id != "anonymous":
        rows = [r for r in rows if r.get("user_id") == user_id]
    sorted_rows = sorted(rows, key=lambda r: r.get("created_at", ""), reverse=True)

    if include_items:
        enriched = []
        for r in sorted_rows:
            r_copy = dict(r)
            r_copy["line_items"] = [
                li for li in _line_items.values()
                if li.get("receipt_id") == r.get("id")
            ]
            enriched.append(r_copy)
        return enriched

    return sorted_rows


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
    bbox: Optional[Dict[str, Any]] = None,
) -> Dict:
    item_id = str(uuid.uuid4())
    cat_id = get_category_id(category) or get_category_id("Miscellaneous") or list(_categories.keys())[0]

    row = {
        "id": item_id,
        "receipt_id": receipt_id,
        "category_id": cat_id,
        "category_name": category,
        "raw_text": raw_text,
        "item_name": item_name,
        "quantity": float(quantity),
        "unit": unit,
        "unit_price": float(unit_price),
        "total_price": float(total_price),
        "confidence_score": float(confidence_score),
        "is_verified": is_verified,
        "bbox": bbox,
    }
    _line_items[item_id] = row

    client = get_supabase_client()
    if client:
        db_payload = {
            "id": item_id,
            "receipt_id": receipt_id,
            "category_id": cat_id,
            "raw_text": raw_text,
            "item_name": item_name,
            "quantity": float(quantity),
            "unit": unit,
            "unit_price": float(unit_price),
            "total_price": float(total_price),
            "confidence_score": float(confidence_score),
            "is_verified": is_verified,
        }
        if bbox is not None:
            db_payload["bbox"] = bbox

        try:
            client.table("line_items").insert(db_payload).execute()
        except Exception as exc:
            err_msg = str(exc)
            if "bbox" in err_msg or "PGRST204" in err_msg:
                # Column 'bbox' pending migration in Supabase schema cache; retry without bbox
                try:
                    db_payload.pop("bbox", None)
                    client.table("line_items").insert(db_payload).execute()
                    logger.debug("Inserted line item to Supabase without bbox (migration pending): %s", item_id)
                except Exception as retry_exc:
                    logger.warning("Failed to insert line item to Supabase after stripping bbox: %s", retry_exc)
            else:
                logger.warning("Failed to insert line item to Supabase: %s", exc)

    return row


def get_line_items_for_receipt(receipt_id: str) -> List[Dict]:
    """Retrieve all line items associated with a receipt."""
    client = get_supabase_client()
    if client:
        try:
            res = client.table("line_items").select("*").eq("receipt_id", receipt_id).execute()
            if res.data:
                for item in res.data:
                    item["category_name"] = get_category_name(item.get("category_id", ""))
                    # Preserve runtime bbox if DB table schema has not yet migrated
                    cached = _line_items.get(item["id"])
                    if cached and "bbox" in cached and not item.get("bbox"):
                        item["bbox"] = cached["bbox"]
                    _line_items[item["id"]] = item
                return res.data
        except Exception as exc:
            logger.warning("Supabase get_line_items error: %s", exc)

    return [li for li in _line_items.values() if li.get("receipt_id") == receipt_id]


def get_line_item(item_id: str) -> Optional[Dict]:
    """Retrieve a single line item by ID from cache or database."""
    if item_id in _line_items:
        return _line_items[item_id]
    client = get_supabase_client()
    if client:
        try:
            res = client.table("line_items").select("*").eq("id", item_id).execute()
            if res.data and len(res.data) > 0:
                row = res.data[0]
                row["category_name"] = get_category_name(row.get("category_id", ""))
                _line_items[item_id] = row
                return row
        except Exception as exc:
            logger.warning("Supabase get_line_item error: %s", exc)
    return None


def update_line_item(item_id: str, updates: Dict[str, Any]) -> Optional[Dict]:
    """Update line item fields."""
    if item_id in _line_items:
        _line_items[item_id].update(updates)

    client = get_supabase_client()
    if client:
        try:
            # Clean fields for Supabase table
            db_updates = {k: v for k, v in updates.items() if k != "category_name"}
            client.table("line_items").update(db_updates).eq("id", item_id).execute()
        except Exception as exc:
            logger.warning("Supabase update_line_item error: %s", exc)

    return _line_items.get(item_id)


# ── Deduplication Hashes Persistence ─────────────────────────────────────────

def insert_receipt_hash(receipt_id: str, phash_64: str, text_sha256: str) -> Dict:
    """Stores visual & textual deduplication hashes in Supabase."""
    hash_id = str(uuid.uuid4())
    row = {
        "id": hash_id,
        "receipt_id": receipt_id,
        "phash_64": phash_64,
        "text_fingerprint_sha256": text_sha256,
        "created_at": datetime.utcnow().isoformat(),
    }
    _hashes[receipt_id] = row

    client = get_supabase_client()
    if client:
        try:
            client.table("receipt_hashes").insert({
                "id": hash_id,
                "receipt_id": receipt_id,
                "phash_64": phash_64,
                "text_fingerprint_sha256": text_sha256,
            }).execute()
        except Exception as exc:
            logger.warning("Failed to persist receipt hash to Supabase: %s", exc)

    return row


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
        "model_confidence": float(model_confidence),
        "review_status": "UNRESOLVED",
        "flagged_at": datetime.utcnow().isoformat(),
        "resolved_at": None,
    }
    _review_queue[queue_id] = row

    client = get_supabase_client()
    if client:
        try:
            client.table("review_queue").insert({
                "id": queue_id,
                "line_item_id": line_item_id,
                "candidate_text": candidate_text,
                "model_confidence": float(model_confidence),
                "review_status": "UNRESOLVED",
            }).execute()
        except Exception as exc:
            logger.warning("Failed to insert review queue item to Supabase: %s", exc)

    return row


def get_review_queue(status: str = "UNRESOLVED") -> List[Dict]:
    """Return review queue items enriched with receipt and line item details."""
    client = get_supabase_client()
    if client:
        try:
            q = client.table("review_queue").select("*, line_items(*, receipts(*))")
            if status != "ALL":
                q = q.eq("review_status", status)
            q = q.order("flagged_at", desc=True)
            res = q.execute()

            if res.data:
                enriched = []
                for item in res.data:
                    li_data = item.get("line_items") or {}
                    rcpt_data = li_data.get("receipts") or {}
                    li_data["category_name"] = get_category_name(li_data.get("category_id", ""))
                    enriched.append({
                        "id": item["id"],
                        "line_item_id": item["line_item_id"],
                        "candidate_text": item.get("candidate_text", ""),
                        "model_confidence": item.get("model_confidence", 0.0),
                        "review_status": item.get("review_status", "UNRESOLVED"),
                        "flagged_at": item.get("flagged_at"),
                        "resolved_at": item.get("resolved_at"),
                        "line_item": li_data,
                        "receipt_id": li_data.get("receipt_id"),
                        "merchant_name": rcpt_data.get("merchant_name"),
                    })
                return enriched
        except Exception as exc:
            logger.warning("Supabase get_review_queue query error (%s), using local store", exc)

    # Local fallback
    results = []
    for q in _review_queue.values():
        if q["review_status"] != status and status != "ALL":
            continue
        li = _line_items.get(q["line_item_id"], {})
        receipt = _receipts.get(li.get("receipt_id", ""), {})
        results.append({
            **q,
            "line_item": li,
            "receipt_id": li.get("receipt_id"),
            "merchant_name": receipt.get("merchant_name"),
        })
    return sorted(results, key=lambda r: r.get("flagged_at", ""), reverse=True)


def resolve_review_queue_item(
    queue_id: str,
    review_status: str,
    confirmed_name: Optional[str] = None,
    confirmed_quantity: Optional[float] = None,
    confirmed_unit: Optional[str] = None,
    confirmed_unit_price: Optional[float] = None,
    confirmed_total_price: Optional[float] = None,
) -> Optional[Dict]:
    """Resolve a review item, updating both review_queue and the target line item."""
    now_str = datetime.utcnow().isoformat()

    # Update in-memory
    if queue_id in _review_queue:
        _review_queue[queue_id]["review_status"] = review_status
        _review_queue[queue_id]["resolved_at"] = now_str
        line_item_id = _review_queue[queue_id]["line_item_id"]
    else:
        line_item_id = None

    updates: Dict[str, Any] = {"is_verified": True}
    if confirmed_name:
        updates["item_name"] = confirmed_name
    if confirmed_quantity is not None:
        updates["quantity"] = float(confirmed_quantity)
    if confirmed_unit:
        updates["unit"] = confirmed_unit
    if confirmed_unit_price is not None:
        updates["unit_price"] = float(confirmed_unit_price)
    if confirmed_total_price is not None:
        updates["total_price"] = float(confirmed_total_price)

    client = get_supabase_client()
    if client:
        try:
            # 1. Update review_queue table
            client.table("review_queue").update({
                "review_status": review_status,
                "resolved_at": now_str,
            }).eq("id", queue_id).execute()

            # 2. Get line_item_id if not found locally
            if not line_item_id:
                rq_row = client.table("review_queue").select("line_item_id").eq("id", queue_id).execute()
                if rq_row.data:
                    line_item_id = rq_row.data[0]["line_item_id"]

            # 3. Update line_item
            if line_item_id:
                update_line_item(line_item_id, updates)
        except Exception as exc:
            logger.warning("Supabase resolve_review_queue_item error: %s", exc)

    if line_item_id:
        update_line_item(line_item_id, updates)

    return _review_queue.get(queue_id)


# ── Analytics Queries ─────────────────────────────────────────────────────────

def get_monthly_summary(year: int, month: int) -> Dict:
    """
    Aggregate spend data for the given year/month.
    Returns category_breakdown, total_spend, receipt_count.
    """
    import calendar as _cal

    period = f"{year:04d}-{month:02d}"
    _, last_day = _cal.monthrange(year, month)

    client = get_supabase_client()
    if client:
        try:
            # Receipts for period
            r_query = client.table("receipts").select("id, total_amount, status") \
                .gte("receipt_date", f"{period}-01") \
                .lte("receipt_date", f"{period}-{last_day:02d}") \
                .neq("status", "DUPLICATE").execute()

            if r_query.data is not None:
                period_receipts = r_query.data
                receipt_ids = [r["id"] for r in period_receipts]
                receipt_count = len(period_receipts)
                total_spend = sum(float(r.get("total_amount", 0.0)) for r in period_receipts)

                category_breakdown: Dict[str, float] = {}
                if receipt_ids:
                    items_res = client.table("line_items").select("total_price, category_id").in_("receipt_id", receipt_ids).execute()
                    if items_res.data:
                        for li in items_res.data:
                            cat_name = get_category_name(li.get("category_id", ""))
                            val = float(li.get("total_price", 0.0))
                            category_breakdown[cat_name] = round(category_breakdown.get(cat_name, 0.0) + val, 2)

                return {
                    "period": period,
                    "total_spend": round(total_spend, 2),
                    "receipt_count": receipt_count,
                    "category_breakdown": category_breakdown,
                }
        except Exception as exc:
            logger.warning("Supabase get_monthly_summary query error: %s", exc)

    # In-memory aggregation fallback
    period_receipts = [
        r for r in _receipts.values()
        if r.get("receipt_date", "").startswith(period) and r.get("status") != "DUPLICATE"
    ]
    receipt_ids = {r["id"] for r in period_receipts}
    items_in_period = [li for li in _line_items.values() if li.get("receipt_id") in receipt_ids]

    total_spend = sum(li.get("total_price", 0.0) for li in items_in_period)
    category_breakdown = {}
    for li in items_in_period:
        cat = li.get("category_name", "Miscellaneous")
        category_breakdown[cat] = round(category_breakdown.get(cat, 0.0) + li.get("total_price", 0.0), 2)

    return {
        "period": period,
        "total_spend": round(total_spend, 2),
        "receipt_count": len(period_receipts),
        "category_breakdown": category_breakdown,
    }


def get_monthly_trend(months: int = 3) -> List[Dict]:
    """Return per-month totals for the past N months (oldest to newest)."""
    results = []
    today = date.today()

    for i in range(months - 1, -1, -1):
        # Step back month-by-month using first-of-month arithmetic (avoids 28/30/31 day ambiguity)
        m = today.month - i
        y = today.year
        while m < 1:
            m += 12
            y -= 1
        summary = get_monthly_summary(y, m)
        results.append(summary)

    return results


# ── Dashboard Groundwork Helpers ─────────────────────────────────────────────

def get_review_summary() -> Dict[str, int]:
    """Return counts of review queue items by status."""
    client = get_supabase_client()
    if client:
        try:
            res = client.table("review_queue").select("review_status").execute()
            if res.data is not None:
                total = len(res.data)
                unresolved = sum(1 for q in res.data if q.get("review_status") == "UNRESOLVED")
                accepted = sum(1 for q in res.data if q.get("review_status") == "ACCEPTED")
                edited = sum(1 for q in res.data if q.get("review_status") == "EDITED")
                return {
                    "total": total,
                    "unresolved": unresolved,
                    "accepted": accepted,
                    "edited": edited,
                }
        except Exception as exc:
            logger.warning("Supabase get_review_summary error: %s", exc)

    total = len(_review_queue)
    unresolved = sum(1 for q in _review_queue.values() if q.get("review_status") == "UNRESOLVED")
    accepted = sum(1 for q in _review_queue.values() if q.get("review_status") == "ACCEPTED")
    edited = sum(1 for q in _review_queue.values() if q.get("review_status") == "EDITED")
    return {
        "total": total,
        "unresolved": unresolved,
        "accepted": accepted,
        "edited": edited,
    }


def get_categories_detailed() -> List[Dict]:
    """Return all categories with aggregated spend and item counts across all receipts."""
    client = get_supabase_client()
    cat_spend: Dict[str, float] = {}
    cat_items: Dict[str, int] = {}
    total_all_spend = 0.0

    if client:
        try:
            items_res = client.table("line_items").select("total_price, category_id").execute()
            if items_res.data:
                for li in items_res.data:
                    cname = get_category_name(li.get("category_id", ""))
                    price = float(li.get("total_price", 0.0))
                    cat_spend[cname] = cat_spend.get(cname, 0.0) + price
                    cat_items[cname] = cat_items.get(cname, 0) + 1
                    total_all_spend += price
        except Exception as exc:
            logger.warning("Supabase get_categories_detailed error: %s", exc)

    if not cat_spend:
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

        cat_breakdown.append({
            "category_name": name,
            "color_hex": meta["color_hex"],
            "description": meta.get("description", ""),
            "total_spend": spend,
            "item_count": 0,
            "percentage_of_total": pct,
        })

    cat_breakdown.sort(key=lambda c: c["total_spend"], reverse=True)
    rev_summary = get_review_summary()

    # Verified items count
    client = get_supabase_client()
    verified_items = 0
    if client:
        try:
            vres = client.table("line_items").select("id", count="exact").eq("is_verified", True).execute()
            verified_items = vres.count or 0
        except Exception:
            verified_items = sum(1 for li in _line_items.values() if li.get("is_verified"))
    else:
        verified_items = sum(1 for li in _line_items.values() if li.get("is_verified"))

    recent = list_receipts()[:5]

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
    Writes to Supabase (and local store) to allow dashboard testing with rich charts.
    """
    today = date.today()
    this_month_str = today.strftime("%Y-%m")
    prev_month_date = today.replace(day=1) - timedelta(days=15)
    prev_month_str = prev_month_date.strftime("%Y-%m")

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
                ("Cooking Oil (Dalda Pouch)", 1.0, "ltr", 530.0, 530.0, 0.72, "Groceries & Food", False),
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
                ("Ambiguous Herbal Balm", 1.0, "box", 190.0, 190.0, 0.69, "Personal Care", False),
            ],
        },
        # --- Previous Month Receipts ---
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
    """Clear all receipts, line items, and review items, re-initializing categories."""
    global _receipts, _line_items, _review_queue, _categories, _hashes
    _receipts.clear()
    _line_items.clear()
    _review_queue.clear()
    _categories.clear()
    _hashes.clear()
    _seed_categories()

    client = get_supabase_client()
    if client:
        try:
            # Cascading delete from receipts clears line_items, hashes, and review_queue
            client.table("receipts").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            logger.info("Cleared all receipts and related records from Supabase")
        except Exception as exc:
            logger.warning("Supabase reset_store error: %s", exc)


# ── Image Storage Operations ──────────────────────────────────────────────────

def _image_store_path() -> "Path":
    """Return the absolute path to the local image store directory, creating it if needed."""
    from pathlib import Path
    base = Path(settings.image_store_dir)
    if not base.is_absolute():
        # Resolve relative to backend/ root (two levels up from this file: services → app → backend)
        base = Path(__file__).resolve().parents[2] / settings.image_store_dir
    base.mkdir(parents=True, exist_ok=True)
    return base


def save_receipt_image(receipt_id: str, image_bytes: bytes, ext: str = "jpg") -> Optional[str]:
    """
    Persist a preprocessed receipt image.

    Strategy (in order of preference):
    1. Upload to Supabase Storage bucket (``receipt-images``) when configured.
    2. Save to local disk under ``settings.image_store_dir``.

    Returns the local file path (str) on success, or None on failure.
    """
    from pathlib import Path

    local_path = _image_store_path() / f"{receipt_id}.{ext}"

    # Always save locally as a reliable fallback
    try:
        local_path.write_bytes(image_bytes)
        logger.debug("Receipt image saved locally: %s", local_path)
    except Exception as exc:
        logger.warning("Failed to save receipt image locally: %s", exc)
        return None

    # Attempt Supabase Storage upload (non-blocking — local copy is the source of truth)
    client = get_supabase_client()
    if client:
        try:
            storage_path = f"{receipt_id}.{ext}"
            client.storage.from_(settings.supabase_storage_bucket).upload(
                path=storage_path,
                file=image_bytes,
                file_options={"content-type": f"image/{ext}", "upsert": "true"},
            )
            logger.info("Receipt image uploaded to Supabase Storage: %s", storage_path)
        except Exception as exc:
            logger.warning("Supabase Storage upload failed (local copy retained): %s", exc)

    return str(local_path)


def get_receipt_image_path(receipt_id: str) -> Optional[str]:
    """
    Return the local filesystem path for a receipt image, or None if not found.
    Searches for any supported extension (jpg, jpeg, png, webp).
    """
    base = _image_store_path()
    for ext in ("jpg", "jpeg", "png", "webp"):
        p = base / f"{receipt_id}.{ext}"
        if p.exists():
            return str(p)
    return None


def get_receipt_image_bytes(receipt_id: str) -> Optional[bytes]:
    """
    Return raw bytes of a receipt image.

    Tries Supabase Storage first (for consistency across server instances), then
    falls back to the local filesystem copy.
    """
    # Try Supabase Storage first
    client = get_supabase_client()
    if client:
        for ext in ("jpg", "jpeg", "png", "webp"):
            try:
                data = client.storage.from_(settings.supabase_storage_bucket).download(
                    f"{receipt_id}.{ext}"
                )
                if data:
                    logger.debug("Receipt image retrieved from Supabase Storage: %s.%s", receipt_id, ext)
                    return data
            except Exception:
                continue

    # Fall back to local disk
    local_path = get_receipt_image_path(receipt_id)
    if local_path:
        try:
            from pathlib import Path
            return Path(local_path).read_bytes()
        except Exception as exc:
            logger.warning("Failed to read local receipt image: %s", exc)

    return None


def get_supabase_image_url(receipt_id: str, expires_in: int = 3600) -> Optional[str]:
    """
    Generate a temporary signed URL for a receipt image stored in Supabase Storage.

    Args:
        receipt_id: UUID of the receipt.
        expires_in: Seconds until the URL expires (default 1 hour).

    Returns:
        Signed URL string, or None if Supabase Storage is unavailable.
    """
    client = get_supabase_client()
    if not client:
        return None

    for ext in ("jpg", "jpeg", "png", "webp"):
        try:
            result = client.storage.from_(settings.supabase_storage_bucket).create_signed_url(
                path=f"{receipt_id}.{ext}",
                expires_in=expires_in,
            )
            url = result.get("signedURL") or result.get("signedUrl")
            if url:
                return url
        except Exception:
            continue

    return None

