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
    r"\b(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>kg|k9|ke|kq|k|g|gm|gram|ltr|liter|litre|l|ml|pkt|packet|pcs|pc|dzn|dozen|dz)\b",
    re.IGNORECASE,
)

# Structured Qty + Unit + Price (e.g. "10kg 1400", "5KG 700.00", "2k 450", "1L 520.00")
_QTY_UNIT_PRICE_RE = re.compile(
    r"(?P<qty>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>kg|k9|ke|kq|k|g|gm|gram|ltr|liter|litre|l|ml|pkt|packet|pcs|pc|dzn|dozen|dz)\s*"
    r"(?:[xX@=:>\-]\s*)?"
    r"(?P<price>\d{2,5}(?:\.\d{1,2})?)"
    r"(?!\s*(?:kg|k9|ke|kq|k|g|gm|gram|ltr|liter|litre|l|ml|pkt|packet|pcs|pc|dzn|dozen|dz)\b)",
    re.IGNORECASE,
)

# Generic quantity + optional unit
_QTY_UNIT_RE = re.compile(
    r"(?P<qty>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>kg|k9|ke|kq|k|g|gm|gram|ltr|liter|litre|l|ml|pkt|packet|pcs|pc|dzn|dozen|dz)?",
    re.IGNORECASE,
)

# Leading item index (e.g. "1. ", "1, ", "2) ", "<> 2. ", "3- ", "C7 4. ", "Zee 2. ")
_LEADING_INDEX_RE = re.compile(r"^\s*(?:[A-Za-z0-9\(\[<>\-~*+.,_]+\s+)?\d+[\.,\)\-:]\s*")

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
    r"pechs|shahrah|karachi|clifton|khi|lahore|islamabad|rawalpindi|jaipur|rajasthan|"
    r"super\s*market|general\s*store|karyana\s*store|karyana|bismillah|imtiaz|al[\s-]?madina|supermarket|subhan|chaudhry|fazal|naheed"
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

        # In receipts, line items strictly precede the subtotal / grand total summary section
        if re.search(r"\b(sub[\s-]?total|grand[\s-]?total|net[\s-]?total|total\s*items|cash\s*paid|change:)\b", line_text, re.IGNORECASE):
            break

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
    Combines direct string similarity, token containment, and Pakistani
    grocery typo mappings (e.g. 'putter' -> 'butter', 'yoourt' -> 'yogurt',
    'deal chana' -> 'daal chana').
    """
    if not _TAXONOMY:
        return None

    query = raw_text.lower().strip()
    if len(query) < 2:
        return None

    # Common OCR misreads on Pakistani receipts & handwriting
    ocr_typo_map = {
        "andas": "andey",
        "anda": "andey",
        "anday": "andey",
        "mikpak": "milkpak",
        "milpak": "milkpak",
        "milkpack": "milkpak",
        "putter": "butter",
        "yoourt": "yogurt",
        "dahl": "dahi",
        "deal": "daal",
        "chavoal": "chawal",
        "cheer": "cheeni",
        "hee": "ghee",
        "aata": "atta",
        "ata": "atta",
        "juic": "juice",
    }
    words = query.split()
    corrected_words = [ocr_typo_map.get(w.strip(".,-"), w) for w in words]
    corrected_query = " ".join(corrected_words)

    # 1. Direct alias match on corrected query
    for entry in _TAXONOMY:
        candidates = entry.aliases + [entry.canonical_name.lower()]
        for alias in candidates:
            alias_lower = alias.lower()
            if alias_lower == corrected_query:
                return entry

    # 2. Token / word containment match
    for entry in _TAXONOMY:
        candidates = entry.aliases + [entry.canonical_name.lower()]
        for alias in candidates:
            alias_lower = alias.lower()
            # If alias is a key product word contained in the query
            if len(alias_lower) >= 4 and any(w == alias_lower for w in corrected_words):
                return entry
            if len(alias_lower) >= 4 and alias_lower in corrected_query:
                return entry

    # 3. Levenshtein ratio matching
    best_score = 0.0
    best_entry: Optional[TaxonomyEntry] = None

    for entry in _TAXONOMY:
        candidates = entry.aliases + [entry.canonical_name.lower()]
        for alias in candidates:
            alias_lower = alias.lower()
            score = levenshtein_ratio(corrected_query, alias_lower)
            if score > best_score:
                best_score = score
                best_entry = entry

    if best_score >= settings.fuzzy_match_threshold:
        logger.debug(
            "Fuzzy match: '%s' -> '%s' (score=%.2f)",
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
    # Correct common OCR confusion between digit '6'/'9'/'b' and unit 'g' for standard packaging grams
    cleaned_line = re.sub(r"\b(100|200|250|400|430|450|500|800|900|1000)[6bB9]\b", r"\1g", cleaned_line)
    # Replace underscores with spaces (e.g. 'Cheeni_3kq_' -> 'Cheeni 3kq ')
    cleaned_line = re.sub(r"_+", " ", cleaned_line)
    # Correct handwritten OCR digit misreads before units (e.g. l0k9/l0kg/1Okg/loka -> 10kg, akg/zkg -> 2kg, tke/1ke -> 1kg, 1dz)
    cleaned_line = re.sub(r"\b[lI|1][oO0]\s*(kg|k9|ke|kq|ka)\b", r"10kg", cleaned_line, flags=re.IGNORECASE)
    cleaned_line = re.sub(r"\b[aAzZ]\s*(kg|k9|ke|kq)\b", r"2kg", cleaned_line, flags=re.IGNORECASE)
    cleaned_line = re.sub(r"\b[tT1]ke\b|\b[tT]kg\b", r"1kg", cleaned_line, flags=re.IGNORECASE)
    cleaned_line = re.sub(r"\b(1|i|l|t)\s*(de|dz|dze|dzn|da)\b", r"1dz", cleaned_line, flags=re.IGNORECASE)
    # Correct handwritten 1400 price misreads (e.g. '“t4oo', 't400', '14oo')
    cleaned_line = re.sub(r"(?:[“\"'\b]|^)[tT1]4[oO0]{2}\b", r" 1400", cleaned_line)
    # Collapse duplicate adjacent quantity tokens (e.g. '10kg 10kg' -> '10kg')
    cleaned_line = re.sub(r"\b(\d+(?:\.\d+)?\s*(?:kg|k9|ke|kq|ka|g|gm|ltr|l|ml|pkt|dzn|dz))\s+\1\b", r"\1", cleaned_line, flags=re.IGNORECASE)
    # Strip leading line index
    line_body = _LEADING_INDEX_RE.sub("", cleaned_line).strip()

    # Split embedded total marker from the end of an item line (e.g. "Ghee 500 = 3030=" or "Total = 3030")
    m_embed = re.search(r"(?:total|tole|totl|ٹوٹل|کل)[\s=:_]+(?P<total>\d{2,6})\b|[=:]\s*(?P<total2>\d{2,6})\s*[=:]?$", line_body, re.IGNORECASE)
    if m_embed:
        item_prefix = line_body[:m_embed.start()].strip()
        item_prefix = re.sub(r"^(?:total|tole|totl|ٹوٹل|کل)[\s=:_]+", "", item_prefix, flags=re.IGNORECASE).strip()
        if len(re.sub(r"[^a-zA-Z]", "", item_prefix)) >= 3:
            line_body = item_prefix
        else:
            return None

    # Skip lines that are dates
    if _DATE_RE.search(line_body) and not re.search(r"\b(atta|rice|oil|milk|tea|sugar|bread|eggs|butter|dahi|ghee|soap|chawal|daal|doodh|cheeni|panadol|disprin|sancos|surf|aloo|pyaz|tamatar|adrak|lehsan|ketchup|masala|mask|tuc)\b", line_body, re.IGNORECASE):
        return None

    # ── Path A: Direct structured (Item Name + Qty + Unit + Price) match ──────
    m_struct = _QTY_UNIT_PRICE_RE.search(line_body)
    if m_struct:
        struct_name = line_body[:m_struct.start()].strip()
        struct_name = re.sub(r"^[?><~+*.,_\-|\s]+", "", struct_name).strip()
        struct_name = _LEADING_INDEX_RE.sub("", struct_name).strip()
        if len(re.sub(r"[^a-zA-Z]", "", struct_name)) >= 3:
            qty = float(m_struct.group("qty"))
            unit = _normalise_unit(m_struct.group("unit"))
            total_price = float(m_struct.group("price"))
            # If line has multiple columns (e.g. 'CHAKKI ATTA 5KG 1 700.00 700.00'), check trailing total price
            remaining_after = line_body[m_struct.end():]
            extra_prices = _extract_prices(remaining_after)
            # Only use trailing price if decimal formatted (e.g. '.00') on printed receipts, avoiding Urdu checkmarks (610, 262) on slips
            if extra_prices and any("." in w for w in remaining_after.split()):
                total_price = extra_prices[-1]
            unit_price = round(total_price / qty, 2) if qty > 0 else total_price
            match = fuzzy_match(struct_name)
            canonical = match.canonical_name if match else struct_name.title()
            cat = match.category if match else "Miscellaneous"
            if match and unit == "pcs":
                unit = match.standard_unit
            return LineItemCreate(
                raw_text=line_text,
                item_name=canonical,
                quantity=qty,
                unit=unit,
                unit_price=unit_price,
                total_price=total_price,
                confidence_score=max(confidence, 0.88 if match else 0.65),
                category=cat,
                is_verified=False,
            )

    # ── Path B: General regex extraction ──────────────────────────────────────
    qty, unit = _extract_qty_unit(line_body)

    # Exclude quantity with units from price candidates (e.g. 5KG, 430G shouldn't be prices)
    line_for_prices = _QTY_WITH_UNIT_RE.sub(" ", line_body)
    prices = _extract_prices(line_for_prices)
    if not prices:
        # Check if any standalone price distinct from quantity exists
        all_candidate_prices = _extract_prices(line_body)
        prices = [p for p in all_candidate_prices if abs(p - qty) > 0.001 or p >= 30.0]

    raw_name = _extract_item_name(line_body)
    if not raw_name or len(re.sub(r"[^a-zA-Z]", "", raw_name)) < 3:
        return None

    match = fuzzy_match(raw_name)

    if not prices:
        # Items with quantity but no explicit price written (e.g. daily karyana slip: 'Doodh 2kg', 'Dahi 1kg')
        # Require an explicit quantity/unit in the text to avoid misclassifying margin noise (e.g. 'cata')
        if not match or not _QTY_WITH_UNIT_RE.search(line_body):
            return None
        if unit == "pcs":
            unit = match.standard_unit
        return LineItemCreate(
            raw_text=line_text,
            item_name=match.canonical_name,
            quantity=qty,
            unit=unit,
            unit_price=0.0,
            total_price=0.0,
            confidence_score=round(max(confidence, 0.85), 3),
            category=match.category,
            is_verified=False,
        )

    has_decimals = any("." in w and any(c.isdigit() for c in w) for w in line_body.split())
    if has_decimals or len(prices) == 1:
        total_price = prices[-1]
        unit_price = prices[-2] if len(prices) >= 2 else total_price
    else:
        # Handwritten slip: item price is written first, margin checkmarks/doodles are trailing
        total_price = prices[0]
        unit_price = total_price

    if total_price > 50000.0 or total_price <= 0.0:
        return None
    if unit_price > 50000.0:
        unit_price = total_price

    # Guard: If price was mistakenly captured as quantity for a standard item
    if qty == total_price and total_price >= 30.0:
        qty = 1.0
        unit_price = total_price

    # Guard: If price is unreasonably tiny (<= 15) for a bulk grocery item (kg, dzn, ltr), it's an OCR checkmark/noise
    if total_price <= 15.0 and unit in ("kg", "dzn", "ltr", "l", "pkt"):
        if not _QTY_WITH_UNIT_RE.search(line_body):
            return None
        total_price = 0.0
        unit_price = 0.0

    if match:
        canonical_name = match.canonical_name
        category = match.category
        if unit == "pcs":
            unit = match.standard_unit
        item_conf = max(confidence, 0.85)
    else:
        # Require reasonable confidence and realistic price to prevent OCR noise lines
        if confidence < 0.45 or total_price <= 5.0 or len(re.sub(r"[^a-zA-Z]", "", raw_name)) < 4:
            return None
        canonical_name = raw_name.title()
        category = "Miscellaneous"
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
            val = float(raw)
            if 0 < val <= 50000.0:
                results.append(val)
        except ValueError:
            continue

    if len(results) >= 2:
        # Prefer decimal formatted prices (e.g. 180.00, 340.00) or values >= 20 over single integers (1, 4)
        decimal_or_realistic = [p for p in results if (not p.is_integer() or p >= 20.0)]
        if decimal_or_realistic:
            return decimal_or_realistic
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
    cleaned = _PRICE_RE.sub("", cleaned)
    cleaned = _QTY_WITH_UNIT_RE.sub("", cleaned)
    cleaned = _QTY_UNIT_RE.sub("", cleaned)
    cleaned = re.sub(r"\b(?:Rs\.?|PKR)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[×xX@\-–/|*#:~^\\=]", " ", cleaned)
    cleaned = re.sub(r"\b\d+\b", "", cleaned)
    cleaned = " ".join(cleaned.split()).strip(".,- ")
    return cleaned if len(cleaned) >= 2 else ""


def _is_noise_line(text: str) -> bool:
    """Return True for header/footer lines, metadata, and non-item lines that should be skipped."""
    stripped = text.strip().lower()
    if len(stripped) < 3:
        return True
    if _PHONE_RE.search(stripped):
        return True
    if _ACCOUNT_RE.search(stripped):
        return True
    if _NOISE_RE.search(stripped):
        # Exclude header lines from line items unless grocery items are present
        if not re.search(r"\b(atta|rice|oil|milk|tea|sugar|bread|eggs|butter|dahi|ghee|soap|chawal|daal|doodh|cheeni|panadol|disprin|sancos|surf|aloo|pyaz|tamatar|adrak|lehsan|ketchup|masala|mask|tuc)\b", stripped):
            return True
    if _DATE_RE.search(stripped) and not re.search(r"\b(atta|rice|oil|milk|tea|sugar|bread|eggs|butter|dahi|ghee|soap|chawal|daal|doodh|cheeni|panadol|disprin|sancos|surf|aloo|pyaz|tamatar|adrak|lehsan|ketchup|masala|mask|tuc)\b", stripped):
        return True
    if re.match(r"^[-=*_.~^|#]+$", stripped):
        return True
    return False


def _normalise_unit(unit: str) -> str:
    """Map unit aliases to canonical unit abbreviations."""
    mapping = {
        "gram": "g", "gm": "g",
        "liter": "ltr", "litre": "ltr", "l": "ltr",
        "packet": "pkt",
        "dozen": "dzn", "dz": "dzn",
        "pc": "pcs",
        "k9": "kg", "ke": "kg", "kq": "kg", "k": "kg",
    }
    return mapping.get(unit.lower(), unit.lower())
