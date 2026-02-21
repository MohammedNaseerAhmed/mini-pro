import re
from typing import Dict, List


def _count_double_pairs(text: str) -> float:
    """Return fraction of characters that are part of exact 2x consecutive repeats."""
    doubled = len(re.findall(r"(.)\1", text))
    return doubled * 2 / max(len(text), 1)


def _deduplicate_ocr_chars(text: str) -> str:
    """
    Fix repeated-character OCR artefact from PDF bold/shadow-layer rendering.

    Scanned PDFs often produce exactly 2x or 4x character repeats:
        "MMss.. AAnnjjaallii"   → "Ms. Anjali"     (2x repeat — most common)
        "CCCCRRRRMMMM"          → "CRM"             (4x repeat)
        "PPrraaddeeeepp KKuummaarr" → "Pradeep Kumar" (2x/4x mix)

    Detection: if >15% of consecutive char-pairs in the text are doubled,
    the whole document is treated as a doubled-OCR document and every
    letter/digit/symbol pair is collapsed to a single character.
    """
    pair_ratio = _count_double_pairs(text)

    if pair_ratio > 0.15:
        # High duplication → whole-document 2x collapse first
        def _halve_pairs(m: re.Match) -> str:
            return m.group(0)[::2]  # keep every other char (first of each pair)

        # Collapse runs of 2+ identical chars to 1 (handles 2x AND 4x)
        collapsed = re.sub(r"(.)\1+", r"\1", text)
        return collapsed

    # Low global ratio → only collapse obvious 3+ runs (safer for normal text)
    return re.sub(r"(.)\1{2,}", r"\1", text)


def normalize_text(text: str) -> str:
    text = text or ""
    text = text.replace("\x00", " ")
    text = _deduplicate_ocr_chars(text)          # ← fix repeated-char OCR artefact
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_paragraphs(text: str) -> List[Dict[str, str]]:
    normalized = normalize_text(text)
    raw_parts = [p.strip() for p in re.split(r"\n\s*\n", normalized) if p.strip()]
    if not raw_parts:
        raw_parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", normalized) if s.strip()]
    return [{"para_no": i + 1, "text": p} for i, p in enumerate(raw_parts)]


def detect_language_code(text: str) -> str:
    sample = (text or "")[:4000]
    if re.search(r"[\u0C00-\u0C7F]", sample):
        return "te"
    if re.search(r"[\u0900-\u097F]", sample):
        return "hi"
    if re.search(r"[\u0600-\u06FF]", sample):
        return "ur"
    return "en"


def extract_section_blocks(text: str) -> Dict[str, str]:
    """
    Classify document lines into four buckets: facts, arguments, analysis, decision.
    Default bucket is 'facts' so pre-heading introductory text lands there
    instead of being silently assigned to analysis.
    """
    t = normalize_text(text)
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    buckets: Dict[str, List[str]] = {"facts": [], "arguments": [], "analysis": [], "decision": []}
    current = "facts"       # ← was "analysis" — pre-heading lines are usually the intro/facts

    _FACTS_KW    = ["facts", "background", "brief facts", "brief background", "case background",
                    "parties", "factual", "complaint", "fir", "petition", "plaint"]
    _ARG_KW      = ["argument", "submissions", "contention", "submitted", "urged", "counsel",
                    "pleaded", "respondent submits", "petitioner submits"]
    _ANALYSIS_KW = ["analysis", "reasoning", "discussion", "consideration", "findings",
                    "court observes", "we note", "it is noted"]
    _DECISION_KW = ["decision", "order", "judgment", "conclusion", "held that", "disposed",
                    "decree", "dismissed", "allowed", "granted", "result", "accordingly"]

    for ln in lines:
        lower = ln.lower()
        if any(k in lower for k in _FACTS_KW):
            current = "facts"
            continue
        if any(k in lower for k in _ARG_KW):
            current = "arguments"
            continue
        if any(k in lower for k in _ANALYSIS_KW):
            current = "analysis"
            continue
        if any(k in lower for k in _DECISION_KW):
            current = "decision"
            continue
        buckets[current].append(ln)

    return {k: " ".join(v).strip() for k, v in buckets.items()}

