"""
ReceiptLedger – OpenCV Image Preprocessor
==========================================
Pipeline:
  1. Decode bytes → NumPy array
  2. Auto-rotate via EXIF orientation (phone photos)
  3. Downscale to OCR-friendly size if too large (preserves detail)
  4. Grayscale + Gaussian blur
  5. Canny edge detection
  6. Contour extraction + 4-point Douglas-Peucker approximation
     (only applied if detected quad covers ≥ 15 % of image area)
  7. CLAHE contrast enhancement
  8. Optional: light adaptive denoising
  9. Encode to JPEG bytes

Key design decisions:
  - Adaptive binarization is deliberately NOT applied here.
    Tesseract's LSTM engine (OEM 1) reads grayscale better than
    hard-binarized images, especially for thin thermal-print text.
  - Perspective warp is only applied when the detected rectangle is
    substantially large (≥ 15 % of image area), preventing mis-warp
    on screen UI elements, borders, or partial captures.
"""

from __future__ import annotations

import io
import logging
from typing import Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ExifTags

logger = logging.getLogger(__name__)

# Minimum fraction of image area the detected quad must cover to trigger warp
_MIN_QUAD_AREA_RATIO = 0.15
# Maximum long-edge dimension to feed into OCR (larger images are downscaled)
_OCR_MAX_LONG_EDGE = 2400


# ── Public Interface ──────────────────────────────────────────────────────────

def preprocess_image(image_bytes: bytes) -> Tuple[np.ndarray, bytes]:
    """
    Accept raw image bytes, run the full CV preprocessing pipeline.

    Returns:
        processed_gray (np.ndarray): The processed 2-D grayscale image array
                                      (used downstream by OCR engines).
        jpeg_bytes  (bytes):          JPEG-encoded version of the processed image
                                      (for storage / blob upload).
    """
    # 1 ── Decode + EXIF auto-rotate (fixes upside-down phone captures) ────────
    image = _decode_with_exif_rotation(image_bytes)
    if image is None:
        raise ValueError("Could not decode image – unsupported format or corrupt data.")

    # 2 ── Downscale if the image is very large (preserves OCR quality) ────────
    image = _limit_long_edge(image, _OCR_MAX_LONG_EDGE)
    h_orig, w_orig = image.shape[:2]

    # 3 ── Grayscale + gentle Gaussian blur ────────────────────────────────────
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # 4 ── Corner detection via adaptive paper segmentation ────────────────────
    img_area = h_orig * w_orig
    quad_pts = _detect_receipt_corners(gray, img_area, image_bgr=image)

    # 5 ── Perspective warp (only if quad has substantial perspective distortion or background table) ─
    if quad_pts is not None and _needs_perspective_warp(quad_pts, img_area):
        warped = _four_point_transform(gray, quad_pts)
        if warped.shape[1] > warped.shape[0] * 1.15:
            warped = cv2.rotate(warped, cv2.ROTATE_90_CLOCKWISE)
        logger.debug("Perspective warp applied to isolate receipt paper from background.")
    else:
        warped = gray  # Use native grayscale image to preserve thermal print edge sharpness
        logger.debug("Receipt is already upright; preserving native image resolution.")

    # 6 ── Contrast enhancement: linear percentile stretch ────────────────────
    # Avoids CLAHE grid artifacts on wood tables, paper folds, and thermal dot matrices
    p1, p99 = np.percentile(warped, (1, 99))
    if p99 > p1 + 10:
        enhanced = np.clip((warped - p1) * 255.0 / (p99 - p1), 0, 255).astype(np.uint8)
    else:
        enhanced = warped

    # 7 ── Encode to JPEG ──────────────────────────────────────────────────────
    success, buffer = cv2.imencode(".jpg", enhanced, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not success:
        raise RuntimeError("Failed to encode preprocessed image to JPEG.")

    return enhanced, bytes(buffer)


def assess_blur(image_bytes: bytes) -> float:
    """
    Compute the Laplacian variance of the image as a blur metric.
    Higher value = sharper. Values below ~100 are typically too blurry.

    Returns:
        float: Laplacian variance (blur score).
    """
    np_arr = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(np_arr, cv2.IMREAD_GRAYSCALE)
    if image is None:
        return 0.0
    return float(cv2.Laplacian(image, cv2.CV_64F).var())


def validate_dimensions(image_bytes: bytes, min_width: int = 400, min_height: int = 600) -> bool:
    """
    Check that the image meets minimum resolution requirements.
    Relaxed from 720×1280 to 400×600 to accommodate phone gallery screenshots.
    """
    np_arr = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if image is None:
        return False
    h, w = image.shape[:2]
    # Accept portrait OR landscape orientation
    return (w >= min_width and h >= min_height) or (h >= min_width and w >= min_height)


# ── Private Helpers ───────────────────────────────────────────────────────────

def _decode_with_exif_rotation(image_bytes: bytes) -> Optional[np.ndarray]:
    """
    Decode image bytes and apply EXIF orientation correction.
    Phone cameras embed rotation metadata; OpenCV ignores it.
    """
    try:
        pil_img = Image.open(io.BytesIO(image_bytes))
        # Apply EXIF orientation if present
        try:
            exif = pil_img.getexif()
            orientation_key = next(
                k for k, v in ExifTags.TAGS.items() if v == "Orientation"
            )
            orientation = exif.get(orientation_key, 1)
            rotations = {3: 180, 6: 270, 8: 90}
            if orientation in rotations:
                pil_img = pil_img.rotate(rotations[orientation], expand=True)
        except (StopIteration, AttributeError, Exception):
            pass  # No EXIF or no orientation tag — fine

        pil_img = pil_img.convert("RGB")
        img_array = np.array(pil_img)
        # Convert RGB → BGR for OpenCV
        return cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
    except Exception:
        # Fallback to raw OpenCV decode
        np_arr = np.frombuffer(image_bytes, dtype=np.uint8)
        return cv2.imdecode(np_arr, cv2.IMREAD_COLOR)


def _limit_long_edge(image: np.ndarray, max_px: int) -> np.ndarray:
    """Downscale image so the longest edge ≤ max_px, preserving aspect ratio."""
    h, w = image.shape[:2]
    long_edge = max(h, w)
    if long_edge <= max_px:
        return image
    scale = max_px / long_edge
    new_w, new_h = int(w * scale), int(h * scale)
    return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)


def _detect_receipt_corners(
    gray: np.ndarray,
    image_area: int,
    image_bgr: Optional[np.ndarray] = None,
) -> Optional[np.ndarray]:
    """
    Find the four corners of the receipt in the image using paper segmentation
    (color LAB/HSV when available, Otsu/convex hull fallback).
    Only returns a quad if it covers ≥ _MIN_QUAD_AREA_RATIO of the image area.

    Returns an (4, 2) float32 array of corner coordinates, or None if not found.
    """
    min_area = image_area * _MIN_QUAD_AREA_RATIO

    # 1. Color paper segmentation in LAB & HSV (isolates paper from wood desk / surface clutter)
    if image_bgr is not None and len(image_bgr.shape) == 3 and image_bgr.shape[2] == 3:
        h, w = image_bgr.shape[:2]
        lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB)
        hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
        L = lab[:, :, 0]
        S = hsv[:, :, 1]
        # Receipts have high lightness and low saturation relative to wooden or colored desks
        paper_mask = ((L > 135) & (S < 130)).astype(np.uint8) * 255
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
        clean_mask = cv2.morphologyEx(cv2.morphologyEx(paper_mask, cv2.MORPH_OPEN, k), cv2.MORPH_CLOSE, k)
        contours, _ = cv2.findContours(clean_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best_c = None
        best_score = -1.0
        for c in contours:
            area = cv2.contourArea(c)
            if area < min_area or area > 0.95 * image_area:
                continue
            rect = cv2.boundingRect(c)
            cx = rect[0] + rect[2] / 2.0
            cy = rect[1] + rect[3] / 2.0
            dist_center = np.hypot(cx - w / 2.0, cy - h / 2.0) / np.hypot(w / 2.0, h / 2.0)
            score = area * (1.0 - 0.5 * dist_center)
            if score > best_score:
                best_score = score
                best_c = c
        if best_c is not None:
            rect = cv2.minAreaRect(best_c)
            box = cv2.boxPoints(rect)
            return np.array(box, dtype=np.float32)

    # 2. Grayscale Otsu fallback
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # If background border is mostly white, invert so paper is white foreground
    border = np.concatenate([thresh[0, :], thresh[-1, :], thresh[:, 0], thresh[:, -1]])
    if np.mean(border) > 127:
        thresh = cv2.bitwise_not(thresh)

    # Morphological close to bridge internal text/line gaps inside the paper
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)

    for c in contours[:3]:
        area = cv2.contourArea(c)
        if area < min_area:
            continue
        hull = cv2.convexHull(c)
        peri = cv2.arcLength(hull, True)
        approx = cv2.approxPolyDP(hull, 0.03 * peri, True)
        if len(approx) == 4:
            return approx.reshape(4, 2).astype(np.float32)

        # Fallback to minAreaRect for wrinkled, creased, or torn edges
        rect = cv2.minAreaRect(hull)
        box = cv2.boxPoints(rect)
        if min(rect[1]) > 0:
            aspect = max(rect[1]) / min(rect[1])
            if aspect < 8.0:
                return np.array(box, dtype=np.float32)

    return None


def _order_points(pts: np.ndarray) -> np.ndarray:
    """
    Order four corner points as: [top-left, top-right, bottom-right, bottom-left].
    """
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]   # top-left
    rect[2] = pts[np.argmax(s)]   # bottom-right
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]  # top-right
    rect[3] = pts[np.argmax(diff)]  # bottom-left
    return rect


def _needs_perspective_warp(pts: Optional[np.ndarray], image_area: int) -> bool:
    """
    Check if the detected quadrilateral exhibits perspective distortion or
    occupies a sub-region of a larger desk surface.
    """
    if pts is None:
        return False
    rect = _order_points(pts)
    tl, tr, br, bl = rect
    w_top = np.linalg.norm(tr - tl)
    w_bottom = np.linalg.norm(br - bl)
    h_left = np.linalg.norm(bl - tl)
    h_right = np.linalg.norm(br - tr)

    max_w = max(w_top, w_bottom)
    max_h = max(h_left, h_right)
    if max_w == 0 or max_h == 0:
        return False

    quad_area = cv2.contourArea(rect)
    # If the detected paper slip covers less than 85% of the photo, it's lying on a desk
    # Warping/cropping to the receipt boundaries isolates the text and strips background clutter
    if quad_area < 0.85 * image_area:
        return True

    w_diff = abs(w_top - w_bottom) / max_w
    h_diff = abs(h_left - h_right) / max_h

    angle_top = abs(np.degrees(np.arctan2(tr[1] - tl[1], tr[0] - tl[0])))
    angle_left = abs(np.degrees(np.arctan2(bl[0] - tl[0], bl[1] - tl[1])))

    # Only warp if there is substantial trapezoidal perspective or rotation
    return (w_diff > 0.12 or h_diff > 0.12 or angle_top > 6.0 or angle_left > 6.0)


def _four_point_transform(image: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """
    Apply a perspective warp transform using the four detected corner points.
    """
    rect = _order_points(pts)
    tl, tr, br, bl = rect

    # Compute destination rectangle width
    w_top    = np.linalg.norm(tr - tl)
    w_bottom = np.linalg.norm(br - bl)
    w_max    = int(max(w_top, w_bottom))

    # Compute destination rectangle height
    h_left   = np.linalg.norm(bl - tl)
    h_right  = np.linalg.norm(br - tr)
    h_max    = int(max(h_left, h_right))

    # Guard against degenerate transforms
    if w_max < 50 or h_max < 50:
        logger.debug("Detected quad too small (%dx%d), skipping warp.", w_max, h_max)
        return image

    dst = np.array(
        [[0, 0], [w_max - 1, 0], [w_max - 1, h_max - 1], [0, h_max - 1]],
        dtype=np.float32,
    )
    M = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(image, M, (w_max, h_max))


def _center_crop(image: np.ndarray, ratio: float = 0.90) -> np.ndarray:
    """
    Crop the central `ratio` portion of the image (legacy helper, kept for compatibility).
    """
    h, w = image.shape[:2]
    margin_h = int(h * (1 - ratio) / 2)
    margin_w = int(w * (1 - ratio) / 2)
    return image[margin_h: h - margin_h, margin_w: w - margin_w]
