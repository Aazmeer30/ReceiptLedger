"""
ReceiptLedger – NLP Normalization & Fuzzy Domain Correction
=============================================================
Converts raw OCR output lines into structured, canonical LineItemCreate objects.

Pipeline per text-line:
  1. Regex extraction: quantity, unit, price tokens
  2. Remainder text → raw item name
  3. Pre-indexed O(1) & RapidFuzz match against local_taxonomy.json (threshold ≥ 0.80)
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
from rapidfuzz import fuzz

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


# Fast O(1) pre-indexed taxonomy lookup maps
_TAXONOMY: List[TaxonomyEntry] = []
_EXACT_ALIAS_MAP: Dict[str, TaxonomyEntry] = {}
_NORM_ALIAS_MAP: Dict[str, TaxonomyEntry] = {}


def _build_taxonomy_index(entries: List[TaxonomyEntry]) -> None:
    """Pre-index aliases and canonical names for O(1) rapid dictionary lookup."""
    global _EXACT_ALIAS_MAP, _NORM_ALIAS_MAP
    _EXACT_ALIAS_MAP.clear()
    _NORM_ALIAS_MAP.clear()
    for entry in entries:
        candidates = entry.aliases + [entry.canonical_name.lower()]
        clean_canon = re.sub(r"\(.*?\)", "", entry.canonical_name).strip().lower()
        if clean_canon:
            candidates.append(clean_canon)
        for alias in candidates:
            alias_clean = alias.strip().lower()
            if alias_clean:
                _EXACT_ALIAS_MAP[alias_clean] = entry
                norm = re.sub(r"[^a-z0-9]", "", alias_clean)
                if norm:
                    _NORM_ALIAS_MAP[norm] = entry


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
    _build_taxonomy_index(entries)
    logger.debug("Loaded %d taxonomy entries.", len(entries))
    return entries


# Module-level singleton
_TAXONOMY = _load_taxonomy()


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

# Dimensional specifications (e.g. 35.5x25.5CM, 48MM*100M, 18MM, 100M, 803M#, 7W, 12V, 220V, 50HZ)
_DIMENSION_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:[xX*]\s*\d+(?:\.\d+)?\s*)?(?:cm|mm|m[#*]?|inch|in|ft|w|v|hz|fps|mah|sqft)\b",
    re.IGNORECASE,
)

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

# Stop patterns: Line items strictly precede summary / total / tender sections
_STOP_SECTION_RE = re.compile(
    r"\b("
    r"sub[\s-]?total|grand[\s-]?total|net[\s-]?total|net[\s-]?amount|total\s*sales|"
    r"round(?:ed|ing)?[\s-]?total|total\s*rounded|amount[\s-]?payable|payable[\s-]?amount|"
    r"bill[\s-]?total|total[\s-]?amount|total\s*items?|items?\s*total|total\s*qty|totalgty|totall?ttem|totall?y|"
    r"all\s*pri\s*ce\s*are\s*inclusive|item\s*count|"
    r"item\(s\)\s*\d+|qty\(s\)\s*:\s*\d+|"
    r"total[\s=:]+(?:rm|pkr|rs\.?|\$)?\s*\d|"
    r"cash\s*(?:rm|pkr|rs\.?|\$|paid|tendered|pald|back|[:=])|change\s*(?:rm|pkr|rs\.?|\$|[:=])|"
    r"sales\s*tax|sst|gst\s*inclusive|"
    r"ٹوٹل|کل"
    r")\b",
    re.IGNORECASE,
)

# Strip common receipt header/footer metadata, contact info, banking fields, and noise
_NOISE_RE = re.compile(
    r"\b("
    r"total|grand[\s-]?total|net[\s-]?total|sub[\s-]?total|gross[\s-]?total|amount|vat|gst|gstin|pan|tax|discount|balance|change|cash|"
    r"bill|bill\s*to|ship\s*to|sold\s*to|customer|place\s*of\s*supply|terms|conditions|warranty|signature|signatory|authorised|"
    r"invoice|receipt|sntn|srb|pra|kpra|fbr|ntn|nin|strn|pos|terminal|date|pate|time|tne|items|rate|description|price|qty|"
    r"total\s*items|items\s*total|total\s*qty|item\s*count|"
    r"thank\s*you|branch|tel|phone|mob|mobile|cell|whatsapp|helpline|call|contact|uan|"
    r"raast|transfer|transferred|stan|rrn|iban|account|acct|bank|easypaisa|jazzcash|nayapay|sadapay|wallet|"
    r"pechs|shahrah|karachi|clifton|khi|lahore|islamabad|rawalpindi|jaipur|rajasthan|"
    r"jalan|jln|taman|lorong|floor|lot\s*\d+|avenue|damansara|shah\s*alam|johor\s*bahru|grindelwald|entspricht|mwst|"
    r"selangor|kembangan|klang|bandar|seksyen|bukit|raja|setia\s*alam|utama|kathmandu|narephat|batangkali|subtotat|tender|"
    r"service\s*charge|service\s*tax|saving|rounding|co(?:mpany)?\s*reg|reg\s*ma|table\s*:\s*|able\s*:\s*bar|speed\s*mart|"
    r"cashier|server|table|pax|guest\s*check|order\s*taker|open\s*:\s*\d+|doc\s*no|document\s*no|inv\s*:\s*|invoice\s*no|co\s*reg|gst\s*reg|reg\s*no|tax\s*invoice|cash\s*bill|tel/fax|fax|"
    r"super\s*market|general\s*store|karyana\s*store|karyana|bismillah|imtiaz|al[\s-]?madina|supermarket|subhan|chaudhry|fazal|naheed"
    r")\b",
    re.IGNORECASE,
)
_PHONE_RE = re.compile(
    r"\b(?:03\d{2}[-\s]?\d{7}|0\d{2,3}[-\s]?\d{6,8}|\+?92[-\s]?\d{3}[-\s]?\d{7}|uan\b|uan\s*[:;]?\s*\+?\d+)\b",
    re.IGNORECASE,
)
_ACCOUNT_RE = re.compile(r"\b(?:stan|rrn|iban|acct|acc)\s*[:#]?\s*\d+\b", re.IGNORECASE)

# Common OCR misreads on Pakistani receipts & Roman Urdu variations
_OCR_TYPO_MAP: Dict[str, str] = {
    "witha": "sweet melon",
    "withaperkg": "sweet melon",
    "spnch": "spinach",
    "spnchperkg": "spinach",
    "disposibe": "disposable",
    "gass": "glass",
    "mi": "mineral",
    "rot": "roti",
    "alu": "aloo",
    "piaz": "pyaz",
    "tmatar": "tamatar",
    "timatar": "tamatar",
    "lehsan": "lehsan",
    "lahsun": "lehsan",
    "lasun": "lehsan",
    "adrak": "adrak",
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
    "chini": "cheeni",
    "hee": "ghee",
    "aata": "atta",
    "ata": "atta",
    "juic": "juice",
    "ketchp": "ketchup",
    "mayo": "mayonnaise",
    "safguard": "safeguard",
    "colgat": "colgate",
}


# ── Public Interface ──────────────────────────────────────────────────────────

def _clean_retail_item_text(text: str) -> str:
    """
    Strip supermarket barcode numbers, weight specifiers (e.g. 'PER KG 0.640 a'),
    multipliers, and formatting artifacts from an item description.
    """
    s = text
    s = re.sub(r"^\s*(?:\d{4,16}\s+)+", "", s)
    s = re.sub(
        r"\bPER\s+(?:KG|K9|KE|KQ|LTR|L|DZ|DZN|PC|PCS|GM|G|PKT)\b(?:\s+\d+(?:\.\d+)?\s*[a-zA-Z]?)?",
        "",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"\s+[a-zA-Z]$", "", s)
    s = _DIMENSION_RE.sub(" ", s)
    s = re.sub(r"\b(?:Rs\.?|PKR|RM|CHF|EUR|USD|\$|SR|GST|VAT|TX)\b", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"[×xX@\-–/|*#:~^\\=\(\)\[\]\{\}“”\"_]+", " ", s)
    return " ".join(s.split()).strip(".,- ")


def _is_price_continuation_line(text: str) -> bool:
    """
    Check if a receipt line is a supermarket pricing table row (e.g. Metro / Carrefour / Imtiaz)
    containing multi-column prices (e.g. '199.00 199.00 199.00 127.36 0.00 0.00 127.96')
    and no real product description.
    """
    stripped = text.strip()
    if not stripped:
        return False
    if _STOP_SECTION_RE.search(stripped):
        return False
    decimals = re.findall(r"\b\d+[.,]\d{2}\b", stripped)
    letters = re.findall(r"[A-Za-z]", stripped)
    return len(decimals) >= 1 and len(letters) <= 5


def _fold_continuation_lines(text_lines: List[List[OCRToken]]) -> List[List[OCRToken]]:
    """
    Fold multi-line retail item blocks:
    In many POS and supermarket receipts (e.g. Metro, Carrefour, Imtiaz), an item spans 2 lines:
      Line 1: Item description + barcode / weight (e.g. '129728 WITHA PER KG 0.640 a')
      Line 2: Pricing table columns (e.g. '199.00 199.00 199.00 127.36 0.00 0.00 127.96')
    """
    merged_lines: List[List[OCRToken]] = []
    i = 0
    n = len(text_lines)

    while i < n:
        lt = " ".join(t.text for t in text_lines[i]).strip()

        # Stop looking ahead if reaching receipt total/summary
        if _STOP_SECTION_RE.search(lt):
            merged_lines.append(text_lines[i])
            i += 1
            continue

        # Do not fold continuation lines onto non-item noise headers
        if _is_noise_line(lt):
            merged_lines.append(text_lines[i])
            i += 1
            continue

        folded = False
        if i + 1 < n:
            next_lt = " ".join(t.text for t in text_lines[i + 1]).strip()
            if not _STOP_SECTION_RE.search(next_lt):
                if _is_price_continuation_line(next_lt) or re.search(
                    r"\b(?:\d{6,16}\s+)?(?:\d+\s*[xX*@]\s*)?(?:RM|Rs\.?|\$)?\s*\d+[.,]\d{2}\b",
                    next_lt,
                ):
                    combined_tokens = text_lines[i] + text_lines[i + 1]
                    merged_lines.append(combined_tokens)
                    i += 2
                    folded = True
        if not folded:
            merged_lines.append(text_lines[i])
            i += 1

    return merged_lines


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

    # Pre-pass: fold retail continuation lines (item title on line 1, barcode + price on line 2)
    processed_lines = _fold_continuation_lines(text_lines)

    for line_tokens in processed_lines:
        line_text = " ".join(t.text for t in line_tokens).strip()
        if not line_text or _is_noise_line(line_text):
            continue

        # In receipts, line items strictly precede the subtotal / grand total summary section
        if _STOP_SECTION_RE.search(line_text):
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
    Combines O(1) pre-indexed alias lookups, domain typo corrections,
    retail artifact cleaning, and RapidFuzz multi-metric scoring.
    """
    if not _TAXONOMY:
        return None

    query = raw_text.lower().strip()
    if len(query) < 2:
        return None

    # 1. Exact alias lookup (O(1))
    if query in _EXACT_ALIAS_MAP:
        return _EXACT_ALIAS_MAP[query]
    norm_q = re.sub(r"[^a-z0-9]", "", query)
    if norm_q in _NORM_ALIAS_MAP:
        return _NORM_ALIAS_MAP[norm_q]

    # 2. Clean retail artifacts (strip barcodes, 'PER KG', dimension tokens)
    cleaned = _clean_retail_item_text(query)
    if cleaned in _EXACT_ALIAS_MAP:
        return _EXACT_ALIAS_MAP[cleaned]
    norm_c = re.sub(r"[^a-z0-9]", "", cleaned)
    if norm_c in _NORM_ALIAS_MAP:
        return _NORM_ALIAS_MAP[norm_c]

    # 3. Apply domain typo corrections
    words = (cleaned or query).split()
    corrected_words = [_OCR_TYPO_MAP.get(w.strip(".,-"), w) for w in words]
    corrected_query = " ".join(corrected_words)

    if corrected_query in _EXACT_ALIAS_MAP:
        return _EXACT_ALIAS_MAP[corrected_query]
    norm_corr = re.sub(r"[^a-z0-9]", "", corrected_query)
    if norm_corr in _NORM_ALIAS_MAP:
        return _NORM_ALIAS_MAP[norm_corr]

    # 4. Check distinctive core staple words if surrounded by OCR noise
    for w in corrected_words:
        if len(w) >= 3 and w in _EXACT_ALIAS_MAP:
            return _EXACT_ALIAS_MAP[w]

    # 5. RapidFuzz Token-Set & Token-Sort scoring
    best_score = 0.0
    best_entry: Optional[TaxonomyEntry] = None

    q_words = corrected_query.split()

    for entry in _TAXONOMY:
        candidates = entry.aliases + [entry.canonical_name.lower()]
        for alias in candidates:
            alias_lower = alias.lower()
            a_words = alias_lower.split()

            std_ratio = fuzz.ratio(corrected_query, alias_lower)
            token_set = fuzz.token_set_ratio(corrected_query, alias_lower)
            token_sort = fuzz.token_sort_ratio(corrected_query, alias_lower)

            # Single-word alias (e.g. "atta", "rice", "oil", "tissue", "tea")
            if len(a_words) == 1:
                if len(q_words) == 1:
                    score = std_ratio / 100.0
                elif len(q_words) == 2 and a_words[0] in q_words:
                    score = 0.88
                else:
                    score = (token_sort * 0.70 + std_ratio * 0.30) / 100.0
            else:
                score = (token_set * 0.70 + token_sort * 0.30) / 100.0

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
    """
    # Clean quotes, non-standard apostrophes, and leading noise characters
    cleaned_line = re.sub(r"[\u2018\u2019\u201c\u201d'\"`]", "", line_text)
    cleaned_line = re.sub(r"^[?><~+*.,_\-|\s]+", "", cleaned_line).strip()
    # Strip leading repeated SKU/barcode numbers (e.g. '129728 129728 ')
    cleaned_line = re.sub(r"^\s*(?:\d{4,16}\s+)+", "", cleaned_line)
    # Strip long numeric barcodes / SKUs (> 6 digits)
    cleaned_line = re.sub(r"\b\d{7,16}\b", " ", cleaned_line)
    # Strip leading 3-6 digit SKU/PLU code if followed by letters (e.g. "2504 YORCCHUN LOKAM" -> "YORCCHUN LOKAM")
    cleaned_line = re.sub(r"^\s*\d{3,6}\s+([A-Za-z])", r"\1", cleaned_line)
    # Convert decimal commas to dots when flanked by digits (e.g. "9,00" -> "9.00", "74,90" -> "74.90")
    cleaned_line = re.sub(r"(\d+),(\d{2})\b", r"\1.\2", cleaned_line)
    # Collapse split decimal prices and weights (e.g. "160 .00" -> "160.00", "0. 640" -> "0.640")
    cleaned_line = re.sub(r"\b(\d+)\s*\.\s*(\d+)\b", r"\1.\2", cleaned_line)
    # Collapse duplicate adjacent decimal artifacts (e.g. "0.700 700." -> "0.700")
    cleaned_line = re.sub(r"\b0\.(\d{2,3})\s+\1[.,]?\b", r"0.\1", cleaned_line)
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
    if _DATE_RE.search(line_body) and not re.search(r"\b(atta|rice|oil|milk|tea|sugar|bread|eggs|butter|dahi|ghee|soap|chawal|daal|doodh|cheeni|panadol|disprin|sancos|surf|aloo|pyaz|tamatar|adrak|lehsan|ketchup|masala|mask|tuc|water|glass|roti|nihari)\b", line_body, re.IGNORECASE):
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
    line_for_prices = re.sub(
        r"\bPER\s+(?:KG|K9|KE|KQ|LTR|L|DZ|DZN|PC|PCS|GM|G|PKT)\s+\d+(?:\.\d+)?\b",
        " ",
        line_for_prices,
        flags=re.IGNORECASE,
    )
    prices = _extract_prices(line_for_prices)
    if not prices:
        all_candidate_prices = _extract_prices(line_body)
        prices = [p for p in all_candidate_prices if abs(p - qty) > 0.001 or p >= 20.0]

    raw_name = _extract_item_name(line_body)
    if not raw_name or len(re.sub(r"[^a-zA-Z]", "", raw_name)) < 2:
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
    if len(prices) >= 3 and has_decimals:
        # Multi-column table (e.g. Metro / Carrefour / Imtiaz)
        # prices: [unit_price, base_price, net_price, ..., total_price]
        total_price = prices[-1]
        unit_price = prices[0]
        # If first price token is an OCR artifact or misaligned, recompute unit_price
        if qty > 1.0 and abs(qty * unit_price - total_price) > 5.0:
            unit_price = round(total_price / qty, 2)
    elif has_decimals or len(prices) == 1:
        total_price = prices[-1]
        unit_price = prices[-2] if len(prices) >= 2 else total_price
    else:
        # If multiple integer prices on handwritten slip, e.g. 'Rot 6 150':
        if len(prices) == 2 and prices[0].is_integer() and 1 <= prices[0] <= 50 and prices[1] > prices[0]:
            qty = prices[0]
            total_price = prices[1]
            unit_price = round(total_price / qty, 2)
        else:
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
        if confidence < 0.45 or total_price <= 5.0 or len(re.sub(r"[^a-zA-Z]", "", raw_name)) < 3:
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
    clean_text = _DIMENSION_RE.sub(" ", text)
    results = []
    for match in _PRICE_RE.finditer(clean_text):
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
    Prioritises explicit units (e.g. 5kg, 2L, 500g) and produce weighing syntax (PER KG 0.640).
    Returns (1.0, 'pcs') as default if nothing is found.
    """
    clean_text = _DIMENSION_RE.sub(" ", text)

    # 1. Produce weighing syntax: PER KG 0.640
    m_per = re.search(
        r"\bPER\s+(?P<unit>KG|K9|KE|KQ|LTR|L|DZ|DZN|PC|PCS|GM|G|PKT)\s+(?P<qty>\d+(?:\.\d+)?)\b",
        clean_text,
        re.IGNORECASE,
    )
    if m_per:
        return float(m_per.group("qty")), _normalise_unit(m_per.group("unit"))

    # 2. Standard quantity with unit: 5kg, 500g, 1dz
    m = _QTY_WITH_UNIT_RE.search(clean_text)
    if m:
        qty_str = m.group("qty")
        unit_str = (m.group("unit") or "pcs").lower()
        return float(qty_str), _normalise_unit(unit_str)

    # 3. Multiplier syntax: 2x, 6X, 3 *
    m_mult = re.search(r"\b(?P<qty>\d+)\s*[xX*@]\b|\b[xX*@]\s*(?P<qty2>\d+)\b", clean_text)
    if m_mult:
        qty_val = float(m_mult.group("qty") or m_mult.group("qty2"))
        if 0 < qty_val <= 100:
            return qty_val, "pcs"

    return 1.0, "pcs"


def _extract_item_name(text: str) -> str:
    """
    Strip price, quantity, and dimensional tokens from the line to isolate the item description.
    Preserves English alphabet characters in food names.
    """
    cleaned = _clean_retail_item_text(text)
    cleaned = _PRICE_RE.sub("", cleaned)
    cleaned = _QTY_WITH_UNIT_RE.sub("", cleaned)
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
    # Filter pure postal code or town address lines
    if re.search(r"^\s*\d{4,5}(?:\s+\d{2,4})?\s+[A-Za-z\s,.-]+$", stripped):
        return True
    if _NOISE_RE.search(stripped):
        if not re.search(
            r"\b(atta|rice|oil|milk|tea|sugar|bread|eggs|butter|dahi|ghee|soap|chawal|daal|doodh|cheeni|panadol|disprin|sancos|surf|aloo|pyaz|tamatar|adrak|lehsan|ketchup|masala|mask|tuc|water|glass|roti|nihari|haleem|karahi|tikka|biryani|pulao|naan|shampoo)\b",
            stripped,
        ):
            return True
    if _DATE_RE.search(stripped) and not re.search(
        r"\b(atta|rice|oil|milk|tea|sugar|bread|eggs|butter|dahi|ghee|soap|chawal|daal|doodh|cheeni|panadol|disprin|sancos|surf|aloo|pyaz|tamatar|adrak|lehsan|ketchup|masala|mask|tuc|water|glass|roti|nihari|haleem|karahi|tikka|biryani|pulao|naan|shampoo)\b",
        stripped,
    ):
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
