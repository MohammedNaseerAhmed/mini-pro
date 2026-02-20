import re
from typing import Dict, List

from backend.ai.text_pipeline import extract_section_blocks, normalize_text


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", normalize_text(text)) if s.strip()]


def _take_lines(text: str, min_n: int, max_n: int) -> List[str]:
    sents = _sentences(text)
    if len(sents) >= max_n:
        return sents[:max_n]
    if len(sents) >= min_n:
        return sents[: len(sents)]
    if sents:
        extra = [sents[-1]] * (min_n - len(sents))
        return (sents + extra)[:min_n]
    return []


def summarize_structured(text: str) -> Dict[str, object]:
    text = normalize_text(text)
    if len(text) < 80:
        return {
            "short_summary": "Text too short to summarize.",
            "detailed_summary": "Not enough content available.",
            "key_points": ["Insufficient text for legal summarization."],
        }

    blocks = extract_section_blocks(text)
    facts = blocks.get("facts") or text[:2000]
    arguments = blocks.get("arguments") or text[:2000]
    analysis = blocks.get("analysis") or text[:2200]
    decision = blocks.get("decision") or text[-1200:]

    short_lines = _take_lines(facts + " " + decision, 3, 5)
    short_summary = "\n".join(short_lines)

    detailed_parts = [
        f"Facts: {(' '.join(_take_lines(facts, 2, 3)) or 'Not clearly identified.')}",
        f"Issues/Arguments: {(' '.join(_take_lines(arguments, 2, 3)) or 'Not clearly identified.')}",
        f"Reasoning: {(' '.join(_take_lines(analysis, 2, 3)) or 'Not clearly identified.')}",
        f"Decision: {(' '.join(_take_lines(decision, 1, 2)) or 'Not clearly identified.')}",
    ]
    detailed_summary = "\n".join(detailed_parts)

    key_source = " ".join([facts, arguments, analysis, decision])
    points = _take_lines(key_source, 6, 10)
    key_points = points[:10] if len(points) >= 6 else (points + [points[-1]] * (6 - len(points)) if points else [])
    if not key_points:
        key_points = ["Unable to extract legal key points from the text."]

    return {
        "short_summary": short_summary,
        "detailed_summary": detailed_summary,
        "key_points": key_points[:10],
    }


def summarize_judgment(text: str) -> str:
    s = summarize_structured(text)
    return "\n".join([f"- {p}" for p in s["key_points"]])
