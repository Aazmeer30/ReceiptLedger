"""
ReceiptLedger – Tesseract 5 OCR Client
========================================
Wraps pytesseract with the page segmentation mode and character whitelists
specified in docs/09_DEVELOPMENT_PLAN.md.

Primary configuration:
  --oem 1  → LSTM neural net engine
  --psm 6  → Assume uniform block of text

Digit-only secondary pass (for price validation):
  --psm 10 -c tessedit_char_whitelist=0123456789.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import List

import numpy as np
import pytesseract
from pytesseract import Output

from app.core.models import BoundingBox, OCRToken

logger = logging.getLogger(__name__)

# Auto-detect Tesseract binary on Windows if not on system PATH
_DEFAULT_WIN_PATHS = [
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
]
if not shutil.which("tesseract"):
    for win_path in _DEFAULT_WIN_PATHS:
        if win_path.exists():
            pytesseract.pytesseract.tesseract_cmd = str(win_path)
            break

# Auto-detect local project tessdata directory if available
_LOCAL_TESSDATA = Path(__file__).resolve().parents[2] / "tessdata"
if _LOCAL_TESSDATA.exists() and "TESSDATA_PREFIX" not in os.environ:
    os.environ["TESSDATA_PREFIX"] = str(_LOCAL_TESSDATA)

# Primary Tesseract config for receipts: PSM 6 assumes a uniform block of text (single column/receipt)
_FULL_TEXT_CONFIG = "--oem 1 --psm 6"
# Digit-only config used when validating numeric tokens (prices, quantities)
_DIGIT_CONFIG = "--psm 10 -c tessedit_char_whitelist=0123456789."


def _get_ocr_lang() -> str:
    """Return 'eng+urd' if Urdu traineddata is present in tessdata, else 'eng'."""
    try:
        tess_prefix = os.environ.get("TESSDATA_PREFIX")
        if tess_prefix:
            prefix_path = Path(tess_prefix)
            if (prefix_path / "urd.traineddata").exists() or (prefix_path / "tessdata" / "urd.traineddata").exists():
                return "eng+urd"
        for win_p in _DEFAULT_WIN_PATHS:
            if (win_p.parent / "tessdata" / "urd.traineddata").exists():
                return "eng+urd"
    except Exception:
        pass
    return "eng"


def is_available() -> bool:
    """Return True if Tesseract is installed and callable."""
    try:
        version = pytesseract.get_tesseract_version()
        return version is not None
    except Exception:
        return False


def extract_tokens(
    image: np.ndarray,
    lang: str | None = None,
) -> List[OCRToken]:
    """
    Run Tesseract on the given grayscale image array.
    Uses PSM 6 as primary (uniform text block) and PSM 4 as secondary,
    merging non-overlapping tokens to maximize recall on thermal and handwritten receipts.

    Args:
        image: Preprocessed grayscale 2-D NumPy array.
        lang:  OCR language model to use (e.g. 'eng', 'urd', 'eng+urd').
               Defaults to 'eng'.

    Returns:
        List of OCRToken (text, confidence, bounding_box).
    """
    target_lang = lang if lang is not None else "eng"
    configs = ["--oem 1 --psm 6", "--oem 1 --psm 4"]
    token_passes: List[List[OCRToken]] = []

    for cfg in configs:
        try:
            data = pytesseract.image_to_data(
                image,
                lang=target_lang,
                output_type=Output.DICT,
                config=cfg,
            )
        except Exception as exc:
            logger.error("Tesseract extraction failed (%s, %s): %s", target_lang, cfg, exc)
            continue

        n_boxes = len(data["text"])
        current_tokens: List[OCRToken] = []
        for i in range(n_boxes):
            raw_text = data["text"][i].strip()
            if not raw_text:
                continue

            conf_raw = data["conf"][i]
            if conf_raw < 0:
                continue

            confidence = float(conf_raw) / 100.0

            x = data["left"][i]
            y = data["top"][i]
            w = data["width"][i]
            h = data["height"][i]

            line_id = int(data["block_num"][i]) * 1000 + int(data["line_num"][i])
            current_tokens.append(
                OCRToken(
                    text=raw_text,
                    confidence=min(confidence, 1.0),
                    bounding_box=BoundingBox(
                        x_min=x, y_min=y,
                        x_max=x + w, y_max=y + h,
                    ),
                    line_id=line_id,
                )
            )
        token_passes.append(current_tokens)

    if not token_passes:
        return []

    # Start with the first pass
    merged_tokens: List[OCRToken] = list(token_passes[0])

    # If secondary passes found tokens, merge with confidence replacement
    for sec_pass in token_passes[1:]:
        for t_sec in sec_pass:
            overlap_idx = None
            for idx, t_main in enumerate(merged_tokens):
                dx = abs(t_sec.bounding_box.x_center - t_main.bounding_box.x_center)
                dy = abs(t_sec.bounding_box.y_center - t_main.bounding_box.y_center)
                if dx < 32 and dy < 18:
                    overlap_idx = idx
                    break
            if overlap_idx is not None:
                # If secondary pass token is higher confidence and doesn't truncate text, replace it
                if t_sec.confidence > merged_tokens[overlap_idx].confidence and len(t_sec.text.strip()) >= len(merged_tokens[overlap_idx].text.strip()):
                    merged_tokens[overlap_idx] = t_sec
            elif len(t_sec.text.strip()) > 0:
                merged_tokens.append(t_sec)

    # Always merge sparse text (PSM 11) to capture circled totals or faint rows
    try:
        d11 = pytesseract.image_to_data(
            image,
            lang=target_lang,
            output_type=Output.DICT,
            config="--oem 1 --psm 11",
        )
        for i in range(len(d11["text"])):
            txt = d11["text"][i].strip()
            if not txt or len(txt) == 0:
                continue
            conf = float(d11["conf"][i]) / 100.0 if d11["conf"][i] >= 0 else 0.0
            if conf < 0.10:
                continue
            x, y, w, h = d11["left"][i], d11["top"][i], d11["width"][i], d11["height"][i]
            if w < 4 or h < 6:
                continue
            t_sparse = OCRToken(
                text=txt,
                confidence=min(conf, 1.0),
                bounding_box=BoundingBox(x_min=x, y_min=y, x_max=x + w, y_max=y + h),
                line_id=int(d11["block_num"][i]) * 1000 + int(d11["line_num"][i]),
            )
            overlap_idx = None
            for idx, m in enumerate(merged_tokens):
                if (abs(t_sparse.bounding_box.x_center - m.bounding_box.x_center) < 28
                        and abs(t_sparse.bounding_box.y_center - m.bounding_box.y_center) < 14):
                    overlap_idx = idx
                    break
            if overlap_idx is not None:
                if t_sparse.confidence > merged_tokens[overlap_idx].confidence and len(t_sparse.text.strip()) >= len(merged_tokens[overlap_idx].text.strip()):
                    merged_tokens[overlap_idx] = t_sparse
            else:
                merged_tokens.append(t_sparse)
    except Exception as exc:
        logger.debug("Sparse PSM 11 fallback skipped: %s", exc)

    logger.debug("Tesseract extracted %d merged tokens.", len(merged_tokens))
    return merged_tokens


def validate_digit_token(image_patch: np.ndarray) -> str:
    """
    Run the digit-only whitelist pass on a small image crop (e.g., a price region).
    Used by the dual-pass EasyOCR+Tesseract digit voting step.

    Args:
        image_patch: Cropped grayscale region containing a numeric value.

    Returns:
        str: Recognised digit string (may be empty if unrecognised).
    """
    try:
        result = pytesseract.image_to_string(
            image_patch,
            config=_DIGIT_CONFIG,
        ).strip()
        return result
    except Exception as exc:
        logger.warning("Tesseract digit validation failed: %s", exc)
        return ""
