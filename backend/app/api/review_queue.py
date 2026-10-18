"""
ReceiptLedger – Review Queue Endpoints
GET  /api/v1/review-queue          → Fetch unresolved low-confidence items
PATCH /api/v1/review-queue/{id}    → Human-in-the-loop resolution
GET  /api/v1/review-queue/{id}/crop → Cropped receipt image snippet for visual review

References:
  docs/02_SRS.md § 4.1 (FR-6 Review Queue)
  docs/09_DEVELOPMENT_PLAN.md § 4 (Week 3 / Day 18)
"""

from __future__ import annotations

import io
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Path, status
from fastapi.responses import StreamingResponse

from app.core.models import ReviewQueueItem, ReviewQueueResolveRequest, ReviewStatus
from app.services import store

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/review-queue",
    summary="Fetch items pending human review",
    tags=["Review Queue"],
    responses={
        200: {"description": "List of unresolved low-confidence line items."},
    },
)
async def get_review_queue(
    status_filter: ReviewStatus = ReviewStatus.UNRESOLVED,
) -> List[dict]:
    """
    Returns all review queue items with the given status (default: UNRESOLVED).
    Each item includes the original receipt context and the low-confidence
    raw OCR candidate text for the reviewer to confirm or correct.
    """
    items = store.get_review_queue(status=status_filter.value)
    return items


@router.patch(
    "/review-queue/{queue_id}",
    summary="Resolve a review queue item",
    tags=["Review Queue"],
    responses={
        200: {"description": "Item resolved and line item updated."},
        404: {"description": "Review queue item not found."},
    },
)
async def resolve_review_item(
    queue_id: str = Path(..., description="UUID of the review queue record"),
    payload: ReviewQueueResolveRequest = ...,
) -> dict:
    """
    Human-in-the-loop resolution endpoint.

    The reviewer submits confirmed values (name, quantity, unit, prices).
    The system:
    1. Updates the line_item record with the confirmed values.
    2. Marks the queue item as ACCEPTED or EDITED.
    3. Sets `is_verified = TRUE` on the line item.
    """
    resolved = store.resolve_review_queue_item(
        queue_id=queue_id,
        review_status=payload.action.value,
        confirmed_name=payload.confirmed_name,
        confirmed_quantity=payload.confirmed_quantity,
        confirmed_unit=payload.confirmed_unit,
        confirmed_unit_price=payload.confirmed_unit_price,
        confirmed_total_price=payload.confirmed_total_price,
    )

    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review queue item '{queue_id}' not found.",
        )

    logger.info("Review queue item %s resolved as %s.", queue_id, payload.action.value)
    return resolved


@router.get(
    "/review-queue/{queue_id}/crop",
    summary="Get a cropped receipt image snippet for a review queue item",
    tags=["Review Queue"],
    responses={
        200: {"description": "Cropped JPEG snippet of the receipt around the flagged item."},
        404: {"description": "Review queue item or receipt image not found."},
        503: {"description": "OpenCV not available; cannot produce crop."},
    },
)
async def get_review_crop(
    queue_id: str = Path(..., description="UUID of the review queue record"),
    padding_pct: float = 0.08,
) -> StreamingResponse:
    """
    Return a cropped snippet of the preprocessed receipt image centred around
    the flagged line item.

    Since bounding boxes are not persisted to the database (they are transient
    OCR runtime objects), this endpoint estimates the item's vertical position
    by its ordinal index among the receipt's line items and crops a proportional
    horizontal band, plus ``padding_pct`` of the image height on each side.

    This gives the reviewer enough context to visually verify the OCR reading
    without scrolling through the full receipt image.
    """
    # ── 1. Resolve queue item → line item → receipt ──────────────────────────
    queue_items = store.get_review_queue(status="ALL")
    item = next((q for q in queue_items if q["id"] == queue_id), None)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review queue item '{queue_id}' not found.",
        )

    receipt_id: Optional[str] = item.get("receipt_id")
    line_item_id: str = item.get("line_item_id", "")

    if not receipt_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Could not determine receipt ID for this review item.",
        )

    # ── 2. Load receipt image bytes ──────────────────────────────────────────
    image_bytes = store.get_receipt_image_bytes(receipt_id)
    if not image_bytes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No image found for receipt '{receipt_id}'. "
                   "It may have been processed before image storage was enabled.",
        )

    # ── 3. Compute crop region from line-item ordinal position ───────────────
    try:
        import cv2
        import numpy as np
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenCV is not available; cannot generate image crop.",
        )

    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Stored receipt image could not be decoded.",
        )

    h, w = img.shape[:2]

    # Determine item index and bounding box within all line items for this receipt
    all_items = store.get_line_items_for_receipt(receipt_id)
    target_item = next((li for li in all_items if li.get("id") == line_item_id), None)
    if not target_item or not target_item.get("bbox"):
        cached_li = store.get_line_item(line_item_id)
        if cached_li:
            if not target_item:
                target_item = cached_li
            elif cached_li.get("bbox"):
                target_item["bbox"] = cached_li["bbox"]

    item_ids = [li["id"] for li in all_items]
    try:
        item_idx = item_ids.index(line_item_id)
    except ValueError:
        item_idx = 0
    n_items = max(len(item_ids), 1)

    crop_method = "ordinal_heuristic"
    bbox = target_item.get("bbox") if target_item else None

    # Check if normalized or pixel bounding box is available for pixel-perfect cropping
    if bbox:
        ymin, ymax, xmin, xmax = None, None, None, None
        if isinstance(bbox, dict):
            ymin = bbox.get("ymin") if "ymin" in bbox else bbox.get("y_min")
            ymax = bbox.get("ymax") if "ymax" in bbox else bbox.get("y_max")
            xmin = bbox.get("xmin") if "xmin" in bbox else bbox.get("x_min")
            xmax = bbox.get("xmax") if "xmax" in bbox else bbox.get("x_max")
        elif isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
            ymin, xmin, ymax, xmax = bbox[0], bbox[1], bbox[2], bbox[3]

        if ymin is not None and ymax is not None:
            try:
                ymin_f, ymax_f = float(ymin), float(ymax)
                # If coordinates are normalized (0.0 to 1.0)
                if ymax_f <= 1.0:
                    y_min = max(0, int((ymin_f - padding_pct) * h))
                    y_max = min(h, int((ymax_f + padding_pct) * h))
                else:
                    # Raw pixel coordinates
                    pad_px = int(h * padding_pct)
                    y_min = max(0, int(ymin_f) - pad_px)
                    y_max = min(h, int(ymax_f) + pad_px)

                if y_max > y_min:
                    crop_method = "bbox"
            except (ValueError, TypeError):
                pass

    if crop_method != "bbox":
        # Fall back to ordinal position heuristics:
        # Receipts typically have ~15% header and ~10% footer; body occupies 75%
        header_frac = 0.15
        footer_frac = 0.10
        body_frac = 1.0 - header_frac - footer_frac

        item_center_frac = header_frac + body_frac * ((item_idx + 0.5) / n_items)
        band_half = (body_frac / n_items) / 2 + padding_pct

        y_min = max(0, int((item_center_frac - band_half) * h))
        y_max = min(h, int((item_center_frac + band_half) * h))

    crop = img[y_min:y_max, 0:w]

    # ── 4. Encode and stream as JPEG ─────────────────────────────────────────
    ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to encode crop as JPEG.",
        )

    return StreamingResponse(
        io.BytesIO(buf.tobytes()),
        media_type="image/jpeg",
        headers={
            "Content-Disposition": f'inline; filename="crop_{queue_id}.jpg"',
            "Cache-Control": "private, max-age=300",
            "X-Crop-Method": crop_method,
            "X-Crop-Item-Index": str(item_idx),
            "X-Crop-Item-Count": str(n_items),
            "X-Crop-Y-Min": str(y_min),
            "X-Crop-Y-Max": str(y_max),
        },
    )

