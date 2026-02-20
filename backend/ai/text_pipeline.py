import re
from typing import Dict, List


def normalize_text(text: str) -> str:
    text = text or ""
    text = text.replace("\x00", " ")
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
    t = normalize_text(text)
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    buckets = {"facts": [], "arguments": [], "analysis": [], "decision": []}
    current = "analysis"
    for ln in lines:
        lower = ln.lower()
        if any(k in lower for k in ["facts", "background", "brief facts"]):
            current = "facts"
            continue
        if any(k in lower for k in ["argument", "submissions", "contention"]):
            current = "arguments"
            continue
        if any(k in lower for k in ["analysis", "reasoning", "discussion"]):
            current = "analysis"
            continue
        if any(k in lower for k in ["decision", "order", "judgment", "conclusion", "held that"]):
            current = "decision"
            continue
        buckets[current].append(ln)

    return {k: " ".join(v).strip() for k, v in buckets.items()}
