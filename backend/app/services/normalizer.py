"""
ReceiptLedger – NLP Normalization & Fuzzy Domain Correction
=============================================================
Converts raw OCR output lines into structured, canonical LineItemCreate objects.

Pipeline per text-line:
  1. Regex extraction: quantity, unit, price tokens
  2. Remainder text → raw item name
  3. Levenshtein fuzzy match against local_taxonomy.json (threshold ≥ 0.80)
  4. Canonical mapping: canonical_name, category, standard_unit
  5. Confidence tagging: items below threshold → review queue flag

Regex patterns are specified in docs/09_DEVELOPMENT_PLAN.md § 3.4.

References:
  docs/09_DEVELOPMENT_PLAN.md § 3.4
  docs/03_SDS.md § 2.3
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from Levenshtein import ratio as levenshtein_ratio

from app.core.config import settings
from app.core.models import LineItemCreate, OCRToken

logger = logging.getLogger(__name__)

# ── Taxonomy loading ─────────────────────────────────────────────────────────

_TAXONOMY_PATH = Path(__file__).resolve().parents[3] / "data" / "local_taxonomy.json"

@dataclass
class TaxonomyEntry:
    canonical_name: str
    category: str
    standard_unit: str
    aliases: List[str] = field(default_factory=list)


def _load_taxonomy() -> List[TaxonomyEntry]:
    """Load and validate the local taxonomy dictionary from data/local_taxonomy.json."""
    if not _TAXONOMY_PATH.exists():
        logger.warning("Taxonomy file not found at %s; fuzzy matching disabled.", _TAXONOMY_PATH)
        return []
    with _TAXONOMY_PATH.open(encoding="utf-8") as f:
        raw: List[Dict[str, Any]] = json.load(f)
    entries = []
    for item in raw:
        entries.append(
            TaxonomyEntry(
                canonical_name=item["canonical_name"],
                category=item["category"],
                standard_unit=item["standard_unit"],
                aliases=[a.lower() for a in item.get("aliases", [])],
            )
        )
    logger.debug("Loaded %d taxonomy entries.", len(entries))
    return entries


# Module-level singleton
_TAXONOMY: List[TaxonomyEntry] = _load_taxonomy()


# ── Regex Patterns (from dev plan § 3.4) ────────────────────────────────────

# Quantity with explicit unit (e.g. "5kg", "2.5 ltr", "500g", "1 dozen")
_QTY_WITH_UNIT_RE = re.compile(
    r"\b(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>kg|g|gm|gram|ltr|liter|litre|l|ml|pkt|packet|pcs|pc|dzn|dozen)\b",
    re.IGNORECASE,
)

# Generic quantity + optional unit
_QTY_UNIT_RE = re.compile(
    r"(?P<qty>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>kg|g|gm|gram|ltr|liter|litre|l|ml|pkt|packet|pcs|pc|dzn|dozen)?",
    re.IGNORECASE,
)

# Leading item index (e.g. "1. ", "1, ", "2) ", "<> 2. ", "3- ")
_LEADING_INDEX_RE = re.compile(r"^\s*[\(\[<>\-~*+.,_]*\s*\d+[\.,\)\-:]\s*")

# Price / amount (e.g. "Rs.1450", "PKR 200", "1,450.00", "450")
_PRICE_RE = re.compile(
    r"(?:Rs\.?|PKR\s*)?"
    r"(?P<price>\d{1,6}(?:,\d{3})*(?:\.\d{1,2})?)",
    re.IGNORECASE,
)

# Date pattern (e.g. "09-OCT-2026", "10/10/2026", "2024-05-15")
_DATE_RE = re.compile(
    r"\b(?:\d{1,2}[-/](?:[a-zA-Z]{3}|\d{1,2})[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2})\b",
    re.IGNORECASE,
)

# Strip common receipt header/footer metadata, contact info, banking fields, and noise
_NOISE_RE = re.compile(
    r"\b("
    r"total|grand[\s-]?total|net[\s-]?total|sub[\s-]?total|gross[\s-]?total|amount|vat|gst|gstin|pan|tax|discount|balance|change|cash|"
    r"bill|bill\s*to|ship\s*to|sold\s*to|customer|place\s*of\s*supply|terms|conditions|warranty|signature|signatory|authorised|"
    r"invoice|receipt|ntn|nin|strn|pos|terminal|date|pate|time|tne|items|rate|description|price|qty|"
    r"total\s*items|items\s*total|total\s*qty|item\s*count|"
    r"thank\s*you|branch|tel|phone|mob|mobile|cell|whatsapp|helpline|call|contact|"
    r"raast|transfer|transferred|stan|rrn|iban|account|acct|bank|easypaisa|jazzcash|nayapay|sadapay|wallet|"
    r"pechs|shahrah|karachi|clifton|khi|lahore|islamabad|rawalpindi|jaipur|rajasthan"
    r")\b",
    re.IGNORECASE,
)
_PHONE_RE = re.compile(r"\b(?:03\d{2}[-\s]?\d{7}|0\d{2,3}[-\s]?\d{6,8}|\+?92[-\s]?\d{3}[-\s]?\d{7})\b")
_ACCOUNT_RE = re.compile(r"\b(?:stan|rrn|iban|acct|acc)\s*[:#]?\s*\d+\b", re.IGNORECASE)


# ── Public Interface ──────────────────────────────────────────────────────────

def parse_lines_to_items(
    text_lines: List[List[OCRToken]],
    base_confidence: float = 0.90,
) -> List[LineItemCreate]:
    """
    Convert a list of text lines (each being a list of OCRToken) into
    a list of structured LineItemCreate objects.

    Args:
        text_lines: Output of ocr_router.reassemble_lines().
        base_confidence: Nominal confidence for this OCR result
                         (mean token confidence from the engine).

    Returns:
        List of LineItemCreate ready for deduplication and storage.
    """
    items: List[LineItemCreate] = []

    for line_tokens in text_lines:
        line_text = " ".join(t.text for t in line_tokens).strip()
        if not line_text or _is_noise_line(line_text):
            continue

        # Compute per-line confidence as mean token confidence
        line_conf = (
            sum(t.confidence for t in line_tokens) / len(line_tokens)
            if line_tokens else base_confidence
        )

        item = _parse_single_line(line_text, line_conf)
        if item:
            items.append(item)

    logger.debug("Parsed %d line items from %d text lines.", len(items), len(text_lines))
    return items


def fuzzy_match(raw_text: str) -> Optional[TaxonomyEntry]:
    """
    Find the best matching taxonomy entry for a raw item name string.

    Uses normalised Levenshtein ratio with substring and token containment bonuses:
        Score = 1 - levenshtein_distance(s1, s2) / max(len(s1), len(s2))

    Returns the best entry if score ≥ settings.fuzzy_match_threshold, else None.
    """
    if not _TAXONOMY:
        return None

    query = raw_text.lower().strip()
    if len(query) < 2:
        return None

    best_score = 0.0
    best_entry: Optional[TaxonomyEntry] = None

    for entry in _TAXONOMY:
        candidates = entry.aliases + [entry.canonical_name.lower()]
        for alias in candidates:
            alias = alias.lower()
            if alias == query:
                return entry
            # Substring / token containment bonus (only for substantial queries to avoid 2-letter false matches)
            if len(query) >= 4 and len(alias) >= 4 and (alias in query or query in alias):
                score = max(0.85, levenshtein_ratio(query, alias))
            else:
                score = levenshtein_ratio(query, alias)

            if score > best_score:
                best_score = score
                best_entry = entry

    if best_score >= settings.fuzzy_match_threshold:
        logger.debug(
            "Fuzzy match: '%s' → '%s' (score=%.2f)",
            raw_text, best_entry.canonical_name, best_score,
        )
        return best_entry

    logger.debug("No fuzzy match for '%s' (best score=%.2f).", raw_text, best_score)
    return None


# ── Private Helpers ───────────────────────────────────────────────────────────

def _parse_single_line(line_text: str, confidence: float) -> Optional[LineItemCreate]:
    """
    Extract structured fields from a single receipt line string.

    Strategy:
      - Strip leading junk symbols (e.g. '?', '>', '~').
      - Collapse split decimal prices (e.g. '160 .00' -> '160.00').
      - Strip leading numbering (e.g. '1. ', '1, ', '2) ').
      - Skip if line matches pure date format.
      - Find all price-like numbers; the last one is treated as total_price,
        the second-to-last (if present) as unit_price.
      - Find quantity + unit token.
      - Whatever remains after stripping numeric tokens is the raw item name.
    """
    # Clean leading noise characters
    cleaned_line = re.sub(r"^[?><~+*.,_\-|\s]+", "", line_text).strip()
    # Collapse split decimal prices (e.g. "160 .00" -> "160.00")
    cleaned_line = re.sub(r"(\d+)\s+(\.\d{1,2})\b", r"\1\2", cleaned_line)
    # Correct common OCR confusion between digit '6'/'b' and unit 'g' for standard packaging grams
    cleaned_line = re.sub(r"\b(100|200|250|400|430|450|500|800|900|1000)[6bB]\b", r"\1g", cleaned_line)
    # Strip leading line index
    line_body = _LEADING_INDEX_RE.sub("", cleaned_line).strip()

    # Skip lines that are dates
    if _DATE_RE.search(line_body) and not re.search(r"\b(atta|rice|oil|milk|tea|sugar|bread|eggs|butter|dahi|ghee|soap)\b", line_body, re.IGNORECASE):
        return None

    # Extract quantity + unit
    qty, unit = _extract_qty_unit(line_body)

    # Exclude quantity with units from price candidates (e.g. 5KG, 430G shouldn't be prices)
    line_for_prices = _QTY_WITH_UNIT_RE.sub(" ", line_body)
    prices = _extract_prices(line_for_prices)
    if not prices:
        prices = _extract_prices(line_body)
    if not prices:
        return None  # Lines without any numeric value are unlikely to be items

    total_price = prices[-1]
    unit_price = prices[-2] if len(prices) >= 2 else total_price

    # Guard against phone numbers or huge serial numbers being interpreted as prices
    if total_price > 50000.0 or total_price <= 0.0:
        return None
    if unit_price > 50000.0:
        unit_price = total_price

    # Extract raw item name: remove numeric tokens and currency words
    raw_name = _extract_item_name(line_body)
    if not raw_name or len(re.sub(r"[^a-zA-Z]", "", raw_name)) < 3:
        return None

    # Fuzzy match against taxonomy
    match = fuzzy_match(raw_name)
    if match:
        canonical_name = match.canonical_name
        category = match.category
        if unit == "pcs":  # If unit was not parsed, use standard unit from taxonomy
            unit = match.standard_unit
        item_conf = max(confidence, 0.85)
    else:
        canonical_name = raw_name.title()
        category = "Miscellaneous"
        # UNMATCHED ITEM: Guarantee confidence <= 0.60 so it routes to Review Queue
        item_conf = min(confidence, 0.60)

    return LineItemCreate(
        raw_text=line_text,
        item_name=canonical_name,
        quantity=qty,
        unit=unit,
        unit_price=round(unit_price, 2),
        total_price=round(total_price, 2),
        confidence_score=round(item_conf, 3),
        category=category,
        is_verified=False,
    )


def _extract_prices(text: str) -> List[float]:
    """Extract all price-like float values from a text string."""
    results = []
    for match in _PRICE_RE.finditer(text):
        raw = match.group("price").replace(",", "")
        try:
            results.append(float(raw))
        except ValueError:
            continue
    return results


def _extract_qty_unit(text: str) -> Tuple[float, str]:
    """
    Extract the first (quantity, unit) pair found in the text.
    Prioritises explicit units (e.g. 5kg, 2L, 500g).
    Returns (1.0, 'pcs') as default if nothing is found.
    """
    m = _QTY_WITH_UNIT_RE.search(text)
    if m:
        qty_str = m.group("qty")
        unit_str = (m.group("unit") or "pcs").lower()
        return float(qty_str), _normalise_unit(unit_str)

    m = _QTY_UNIT_RE.search(text)
    if m:
        qty_str = m.group("qty")
        unit_str = (m.group("unit") or "pcs").lower()
        unit_str = _normalise_unit(unit_str)
        try:
            return float(qty_str), unit_str
        except ValueError:
            pass
    return 1.0, "pcs"


def _extract_item_name(text: str) -> str:
    """
    Strip price and quantity tokens from the line to isolate the item description.
    Preserves English alphabet characters (R, P, K, S) in food names.
    """
    cleaned = text
    # Remove price patterns
    cleaned = _PRICE_RE.sub("", cleaned)
    # Remove quantity+unit patterns
    cleaned = _QTY_WITH_UNIT_RE.sub("", cleaned)
    cleaned = _QTY_UNIT_RE.sub("", cleaned)
    # Remove currency words (boundary-checked words only, not character sets!)
    cleaned = re.sub(r"\b(?:Rs\.?|PKR)\b", " ", cleaned, flags=re.IGNORECASE)
    # Remove leading/trailing symbols, separators, and brackets
    cleaned = re.sub(r"[×xX@\-–/|*#:~^\\=]", " ", cleaned)
    # Remove stray digits
    cleaned = re.sub(r"\b\d+\b", "", cleaned)
    # Collapse whitespace
    cleaned = " ".join(cleaned.split()).strip(".,- ")
    return cleaned if len(cleaned) >= 2 else ""


def _is_noise_line(text: str) -> bool:
    """Return True for header/footer lines, metadata, and non-item lines that should be skipped."""
    stripped = text.strip().lower()
    # Skip very short lines
    if len(stripped) < 3:
        return True
    # Skip phone numbers
    if _PHONE_RE.search(stripped):
        return True
    # Skip account numbers, Stan IDs, RRN, IBAN
    if _ACCOUNT_RE.search(stripped):
        return True
    # Skip common receipt noise keywords
    if _NOISE_RE.search(stripped):
        return True
    # Skip lines that are only date or time stamps
    if _DATE_RE.search(stripped) and not re.search(r"\b(atta|rice|oil|milk|tea|sugar|bread|eggs|butter|dahi|ghee|soap)\b", stripped):
        return True
    # Skip lines that are only punctuation / separators
    if re.match(r"^[-=*_.~^|#]+$", stripped):
        return True
    return False


def _normalise_unit(unit: str) -> str:
    """Map unit aliases to canonical unit abbreviations."""
    mapping = {
        "gram": "g", "gm": "g",
        "liter": "ltr", "litre": "ltr", "l": "ltr",
        "packet": "pkt",
        "dozen": "dzn",
        "pc": "pcs",
    }
    return mapping.get(unit.lower(), unit.lower())
