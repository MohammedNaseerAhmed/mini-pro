"""
Section-Aware Summarizer  —  4-Step Pipeline
=============================================

Step 1  Remove header noise (court headings, case numbers, advocate lines, dates)
Step 2  Detect fact paragraphs (allegation, FIR, accused, incident, complaint)
Step 3  Detect decision paragraphs (allowed, dismissed, bail granted, released)
Step 4  Generate human-readable Quick Summary + structured Key Points

Output looks like an explanation written by a person, NOT a paste of legal lines.
"""

import re
from typing import Dict, List, Optional

from backend.ai.groq_client import groq_generate, groq_is_configured
from backend.ai.ollama_client import ollama_generate, ollama_is_configured
from backend.ai.text_pipeline import normalize_text


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1 — HEADER NOISE REMOVAL
# ═══════════════════════════════════════════════════════════════════════════════

# Lines containing these patterns are pure metadata/noise — never put in summary
_HEADER_NOISE_PATTERNS = [
    r"^in the (court|high court|supreme court|district court|sessions|tribunal)",
    r"^before (the hon|hon'ble|magistrate|judge)",
    r"^(present|coram)\s*:",
    r"^case\s*(no|number|id)[\.:# ]",
    r"^\bcc\s*no\b",
    r"^dated[\.:# ]",
    r"^date[\.:# ]",
    r"^(appearance|appearances)\s*:",
    r"^for (the )?(petitioner|respondent|accused|state|appellant|complainant|plaintiff|defendant)\s*:",
    r"^(advocate|adv|counsel|sr\.?\s*counsel|ld\.?\s*counsel)",
    r"^(mr|mrs|ms|dr|smt|shri)\.\s+[a-z].*?adv",
    r"^\s*page\s*\d+",
    r"^\d+\s*$",                            # lone page numbers
    r"^(civil appellate|criminal appellate|original jurisdiction)",
    r"^(writ petition|criminal appeal|civil appeal|mat|fmat|slp)\s*(no|number)?\s*\d",
    r"^(heard on|judgment on|order dated|decided on)\s*:",
    r"^(judgment|order)\s+dated",
    r"^(j\s*u\s*d\s*g\s*m\s*e\s*n\s*t|o\s*r\s*d\s*e\s*r)\s*$",
]

_HEADER_RE = [re.compile(p, re.IGNORECASE) for p in _HEADER_NOISE_PATTERNS]


def _is_noise_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) < 3:
        return True
    if len(stripped) < 60 and stripped.isupper():
        # Short all-caps lines are almost always headers
        return True
    return any(r.match(stripped) for r in _HEADER_RE)


def _remove_header_noise(text: str) -> str:
    """
    Remove the first-page header block and any noise lines throughout.
    Returns only the meaningful body paragraphs.
    """
    lines = text.splitlines()
    clean = []
    consecutive_noise = 0

    for line in lines:
        if _is_noise_line(line):
            consecutive_noise += 1
        else:
            consecutive_noise = 0
            clean.append(line)

    return "\n".join(clean)


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2 — DETECT FACT PARAGRAPHS
# ═══════════════════════════════════════════════════════════════════════════════

_FACT_SIGNALS = [
    "allegation", "alleged", "complaint", "complained",
    "prosecution case", "fir", "first information report",
    "accused", "accused person", "accused is alleged",
    "incident", "occurrence", "offence", "offense",
    "it is stated", "it is alleged", "the case of", "prosecution states",
    "the deceased", "victim", "injured", "administered", "poisoned",
    "arrested", "detention", "in custody", "taken into custody",
    "confessed", "confession", "admitted", "statement of",
    "witness", "evidence", "material on record",
]

_DECISION_SIGNALS = [
    "petition allowed", "application allowed", "appeal allowed",
    "bail granted", "bail is granted", "granted bail",
    "released on bail", "accused released", "set at liberty",
    "petition dismissed", "application rejected", "appeal dismissed",
    "petition stands dismissed", "stands dismissed", "dismissed due to non-prosecution",
    "dismissed for non-prosecution", "dismissed as withdrawn",
    "dismissed", "quashed", "set aside",
    "the court is satisfied", "no merit", "no case",
    "in the result", "in the circumstances", "accordingly",
    "for the foregoing reasons", "in view of",
    "therefore", "thus", "hence", "we hold", "it is held",
    "disposed of", "case is closed",
]

_ARGUMENT_SIGNALS = [
    "learned counsel", "sr. counsel", "senior counsel",
    "it is submitted", "it is contended", "argued that",
    "submitted that", "contended that", "urged that",
    "on behalf of", "for the accused", "for the petitioner",
    "defense argued", "defence argued", "the other side",
    "objected", "opposed", "no opposition",
]


def _score_paragraph(para: str, signals: List[str]) -> int:
    p = para.lower()
    return sum(1 for s in signals if s in p)


def _split_paragraphs(text: str) -> List[str]:
    """Split text into meaningful paragraphs (min 40 chars)."""
    paras = re.split(r"\n{2,}", text)
    result = []
    for p in paras:
        p = p.strip()
        if len(p) >= 40:
            result.append(p)
    return result


def _find_fact_paragraphs(text: str) -> List[str]:
    paras = _split_paragraphs(text)
    scored = [(p, _score_paragraph(p, _FACT_SIGNALS)) for p in paras]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [p for p, score in scored if score >= 1][:4]


def _find_decision_paragraphs(text: str) -> List[str]:
    # Prioritize final part of judgment because outcome is usually there.
    tail = text[-2500:]
    tail_paras = _split_paragraphs(tail)
    full_paras = _split_paragraphs(text)
    paras = full_paras + tail_paras
    scored = []
    for p in paras:
        score = _score_paragraph(p, _DECISION_SIGNALS)
        if p in tail_paras:
            score += 1
        scored.append((p, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [p for p, score in scored if score >= 1][:3]


def _find_argument_paragraphs(text: str) -> List[str]:
    paras = _split_paragraphs(text)
    scored = [(p, _score_paragraph(p, _ARGUMENT_SIGNALS)) for p in paras]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [p for p, score in scored if score >= 1][:2]


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3 — JARGON SIMPLIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

_JARGON = {
    r"\bmaintainable\b":          "acceptable by the court",
    r"\bnot maintainable\b":      "may be rejected by the court",
    r"\blocus standi\b":          "legal right to file this case",
    r"\bdisposed of\b":           "case has been closed",
    r"\bdisposed\b":              "the case is finished",
    r"\bex-parte\b":              "decided without the other side present",
    r"\binter-alia\b":            "among other things",
    r"\binjunction\b":            "court order to stop or allow something",
    r"\bstay order\b":            "temporary pause on a decision",
    r"\bquash(?:ed)?\b":          "cancel / set aside",
    r"\bwrit\b":                  "formal legal request to the court",
    r"\bpetitioner\b":            "the person who filed this case",
    r"\brespondent\b":            "the other party defending the case",
    r"\bplaintiff\b":             "the person who filed this case",
    r"\bdefendant\b":             "the person defending the case",
    r"\bapplicant\b":             "the person who made this request",
    r"\badjournment\b":           "postponing to a later date",
    r"\bsubmission\b":            "argument",
    r"\bcontention\b":            "argument made in court",
    r"\bprima facie\b":           "based on first look",
    r"\bjurisdiction\b":          "legal authority of the court",
    r"\blimitation\b":            "time limit for filing",
    r"\binstant case\b":          "this case",
    r"\bheld\b":                  "the court decided",
    r"\baffidavit\b":             "sworn written statement",
    r"\bencumbrance\b":           "claim or burden on property",
    r"\bcounsel\b":               "lawyer",
    r"\badvocate\b":              "lawyer",
    r"\bgranted\b":               "approved",
    r"\bdismissed\b":             "rejected",
    r"\bappeal\b":                "challenge to a lower court decision",
    r"\bdeposed\b":               "gave testimony",
    r"\bexamined\b":              "questioned in court",
    r"\bremanded\b":              "sent back",
    r"\bin custody\b":            "under arrest",
    r"\bdetained\b":              "held by police",
    r"\bfurnish(?:ing)? (a )?surety\b": "provide a guarantor",
    r"\bfurnish(?:ing)? (a )?bail bond\b": "submit a bail document",
    r"\bpecuniary\b":             "financial",
    r"\bherein\b":                "in this case",
    r"\btherein\b":               "in that",
    r"\bwherein\b":               "where",
    r"\bviz\.?\b":                "that is",
}


def _simplify(text: str) -> str:
    for pattern, replacement in _JARGON.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def _best_sentence(paragraph: str) -> str:
    """Pick the most informative sentence from a paragraph."""
    sentences = re.split(r"(?<=[.!?])\s+", paragraph.strip())
    # Prefer longer, non-header sentences
    good = [s.strip() for s in sentences if len(s.strip()) > 30]
    if not good:
        return paragraph.strip()[:300]
    # Pick the sentence with most signal words
    def score(s):
        sl = s.lower()
        return (
            sum(1 for sig in _FACT_SIGNALS + _DECISION_SIGNALS if sig in sl)
            + len(s) / 500  # slight length bias
        )
    return sorted(good, key=score, reverse=True)[0]


def _extract_outcome_sentence(text: str) -> Optional[str]:
    """
    Extract one grounded outcome sentence from the final section only.
    """
    tail = text[-2500:]
    candidates = [s.strip() for s in re.split(r"(?<=[.!?])\s+", tail) if len(s.strip()) > 15]
    for sentence in candidates:
        sl = sentence.lower()
        if any(
            key in sl for key in [
                "stands dismissed", "dismissed", "allowed", "partly allowed",
                "partly dismissed", "disposed of", "quashed", "rejected", "granted",
            ]
        ):
            return _simplify(sentence)
    return None


def _normalize_sentence_for_dedupe(sentence: str) -> str:
    lowered = sentence.lower().strip()
    lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def _clean_summary(text: str, max_sentences: int = 6) -> str:
    """
    Remove repeated/near-duplicate lines from summary text.
    Keeps first unique occurrences in order.
    """
    if not text:
        return text
    raw_sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    seen = set()
    clean = []
    for sentence in raw_sentences:
        key = _normalize_sentence_for_dedupe(sentence)
        if not key or key in seen:
            continue
        seen.add(key)
        clean.append(sentence)
        if len(clean) >= max_sentences:
            break
    return " ".join(clean).strip() or text.strip()


def _build_llm_summary_prompt(text: str) -> str:
    return (
        "You are a legal summarizer.\n"
        "Return ONLY valid JSON with keys: short_summary, detailed_summary, key_points.\n"
        "Rules:\n"
        "- Use only facts present in TEXT.\n"
        "- Do not guess missing facts.\n"
        "- No repetition.\n"
        "- short_summary: 4-6 sentences.\n"
        "- detailed_summary: include Facts, Arguments, Outcome sections.\n"
        "- key_points: exactly 5 objects, each {\"label\": str, \"explanation\": str}.\n"
        "TEXT:\n"
        f"{text[:5000]}"
    )


def _extract_json_block(payload: str) -> Optional[Dict[str, object]]:
    raw = (payload or "").strip()
    if not raw:
        return None
    try:
        import json
        return json.loads(raw)
    except Exception:
        pass
    m = re.search(r"(\{.*\})", raw, re.DOTALL)
    if not m:
        return None
    try:
        import json
        return json.loads(m.group(1))
    except Exception:
        return None


def _summary_quality_score(summary_obj: Dict[str, object], source_text: str) -> float:
    short = str(summary_obj.get("short_summary") or "").strip()
    detailed = str(summary_obj.get("detailed_summary") or "").strip()
    key_points = summary_obj.get("key_points") or []
    if not short or not detailed or not isinstance(key_points, list):
        return 0.0

    combined = f"{short}\n{detailed}\n" + "\n".join(
        str((kp or {}).get("explanation", "")) if isinstance(kp, dict) else str(kp)
        for kp in key_points
    )
    combined = _clean_summary(combined, max_sentences=10)
    token_re = re.compile(r"[a-zA-Z]{3,}")
    s_tokens = set(token_re.findall(combined.lower()))
    t_tokens = set(token_re.findall((source_text or "").lower()))
    overlap = len(s_tokens & t_tokens) / max(1, len(s_tokens))
    repeat_penalty = 0.2 if len(set(re.split(r"(?<=[.!?])\s+", short.lower()))) < 3 else 0.0
    section_bonus = 0.1 if all(x in detailed.lower() for x in ["facts", "arguments", "outcome"]) else 0.0
    return max(0.0, min(1.0, overlap + section_bonus - repeat_penalty))


def _header_lines(text: str, n: int = 40) -> List[str]:
    return [line.strip() for line in text.splitlines()[:n] if line.strip()]


def _extract_party_from_header(text: str, role: str) -> Optional[str]:
    lines = _header_lines(text, n=50)
    role_up = role.upper()
    for idx, line in enumerate(lines):
        up = line.upper()
        if role_up in up:
            # Prefer current line prefix before marker
            prefix = re.sub(r"\.{2,}", " ", line).strip(" .:-")
            prefix = re.sub(rf"\b{role}\b.*$", "", prefix, flags=re.IGNORECASE).strip(" .:-")
            if re.search(r"[A-Za-z]{2,}", prefix):
                return prefix
            # else inspect previous non-empty line
            if idx > 0:
                candidate = lines[idx - 1].strip(" .:-")
                if re.search(r"[A-Za-z]{2,}", candidate) and "VERSUS" not in candidate.upper():
                    return candidate
    return None


def _validate_llm_summary(llm_result: Dict[str, object], source_text: str) -> bool:
    if not llm_result:
        return False
    score = _summary_quality_score(llm_result, source_text)
    if score < 0.60:
        return False
    combined = (
        str(llm_result.get("short_summary") or "")
        + "\n"
        + str(llm_result.get("detailed_summary") or "")
    ).lower()
    # Hallucination-prone terms must exist in source text too.
    for risky in ["police complaint", "case pending", "allegations to be examined"]:
        if risky in combined and risky not in source_text.lower():
            return False
    return True


def _llm_structured_summary(text: str) -> Optional[Dict[str, object]]:
    prompt = _build_llm_summary_prompt(text)
    candidates: List[Dict[str, object]] = []

    if ollama_is_configured():
        try:
            parsed = _extract_json_block(ollama_generate(prompt))
            if isinstance(parsed, dict):
                candidates.append(parsed)
        except Exception:
            pass
    if groq_is_configured():
        try:
            parsed = _extract_json_block(groq_generate(prompt))
            if isinstance(parsed, dict):
                candidates.append(parsed)
        except Exception:
            pass

    if not candidates:
        return None

    best = max(candidates, key=lambda c: _summary_quality_score(c, text))
    # Basic shape validation
    if not isinstance(best.get("key_points"), list) or len(best.get("key_points")) == 0:
        return None
    return {
        "short_summary": _clean_summary(str(best.get("short_summary") or ""), max_sentences=6),
        "detailed_summary": _clean_summary(str(best.get("detailed_summary") or ""), max_sentences=8),
        "key_points": best.get("key_points")[:5],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4 — GENERATE HUMAN-READABLE OUTPUT
# ═══════════════════════════════════════════════════════════════════════════════

def _build_quick_summary(fact_paras: List[str], decision_paras: List[str],
                         arg_paras: List[str], full_text: str) -> str:
    """
    Build a 4–6 sentence plain-English explanation of the case.
    Never copies raw header lines.
    """
    parts = []

    # Sentence 1 — What the case is about (first fact paragraph)
    if fact_paras:
        s = _simplify(_best_sentence(fact_paras[0]))
        parts.append(s)

    # Sentence 2 — The main allegation (second fact paragraph or second sentence)
    if len(fact_paras) > 1:
        s = _simplify(_best_sentence(fact_paras[1]))
        if s and s != parts[0]:
            parts.append(s)

    # Sentence 3 — What the other side argued
    if arg_paras:
        s = _simplify(_best_sentence(arg_paras[0]))
        parts.append(s)

    # Sentence 4–5 — Court decision
    for dp in decision_paras[:2]:
        s = _simplify(_best_sentence(dp))
        if s not in parts:
            parts.append(s)

    # Fallback: if nothing found, take first meaningful body sentence
    if not parts:
        body = _remove_header_noise(full_text)
        paras = _split_paragraphs(body)
        if paras:
            parts.append(_simplify(_best_sentence(paras[0])))

    if not parts:
        return "Summary could not be generated from the document content."

    return _clean_summary(" ".join(parts[:5]), max_sentences=5)


def _build_key_points(fact_paras: List[str], decision_paras: List[str],
                      arg_paras: List[str], full_text: str) -> List[Dict[str, str]]:
    """
    Build 5 labelled key-point cards.
    Each card has a 'label' and an 'explanation'.
    """
    def get_text(paras: List[str], fallback: str = "") -> str:
        if paras:
            return _simplify(_best_sentence(paras[0]))
        return fallback

    # 1. Who filed the case — derive only from document evidence
    who_text = get_text(
        fact_paras,
        "Not clearly identified in the document."
    )

    # 2. Main issue — from second fact paragraph
    issue_text = get_text(
        fact_paras[1:] if len(fact_paras) > 1 else fact_paras,
        "Main issue is not clearly stated in extractable paragraphs."
    )

    # 3. What the other side says — from argument paragraphs
    defense_text = get_text(
        arg_paras,
        "Arguments are not clearly extractable from the document."
    )

    # 4. What the court examined — from fact paragraph with analytical keywords
    court_text = get_text(
        fact_paras,
        "Court analysis is not clearly extractable from the document."
    )

    # 5. Current status / outcome — from decision paragraph
    outcome_sentence = _extract_outcome_sentence(full_text)
    status_text = get_text(
        decision_paras,
        outcome_sentence or "Final outcome is not clearly identified in the document."
    )

    return [
        {"label": "Who filed the case",    "explanation": who_text},
        {"label": "Main issue",            "explanation": issue_text},
        {"label": "What the other side says", "explanation": defense_text},
        {"label": "What the court examined", "explanation": court_text},
        {"label": "Current status",        "explanation": status_text},
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def summarize_structured(text: str) -> Dict[str, object]:
    """
    Main summarizer entry point.

    Pipeline:
      1. Remove header noise (court name, case number, advocate, dated lines)
      2. Detect fact paragraphs (allegation, FIR, accused, incident)
      3. Detect decision paragraphs (bail granted, dismissed, allowed)
      4. Generate plain-English Quick Summary + 5 Key Points

    Returns:
      {
        "short_summary": str,          # 4–6 sentence paragraph
        "detailed_summary": str,       # section-by-section
        "key_points": list[dict],      # [{label, explanation}, ...]
      }
    """
    text = normalize_text(text)
    if len(text.strip()) < 80:
        return {
            "short_summary": "The document does not have enough text to summarize.",
            "detailed_summary": "Not enough content available.",
            "key_points": [
                {"label": "Note",
                 "explanation": "The uploaded document is too short or could not be read."}
            ],
        }

    # Step 1 — Remove noise
    clean_text = _remove_header_noise(text)

    # Step 2 — Detect fact / decision / argument paragraphs
    fact_paras     = _find_fact_paragraphs(clean_text)
    decision_paras = _find_decision_paragraphs(clean_text)
    arg_paras      = _find_argument_paragraphs(clean_text)

    # Step 3/4 — Generate grounded rule-based summary first
    short_summary = _build_quick_summary(fact_paras, decision_paras, arg_paras, clean_text)
    key_points    = _build_key_points(fact_paras, decision_paras, arg_paras, clean_text)

    # Detailed summary — section blocks for longer view
    def _join(paras: List[str], n: int = 2) -> str:
        return " ".join(
            _simplify(_best_sentence(p)) for p in paras[:n]
        ) or "Not identified in the document."

    outcome_sentence = _extract_outcome_sentence(clean_text)
    detailed_summary = (
        f"Facts: {_join(fact_paras)}\n"
        f"Arguments: {_join(arg_paras)}\n"
        f"Outcome: {outcome_sentence or _join(decision_paras)}"
    )

    petitioner = _extract_party_from_header(text, "Petitioner")
    respondent = _extract_party_from_header(text, "Respondent")
    if petitioner or respondent:
        parties_line = f"Parties: {petitioner or 'Unknown'} vs {respondent or 'Unknown'}."
        short_summary = _clean_summary(f"{parties_line} {short_summary}", max_sentences=6)

    # Accuracy mode: allow LLM refinement only if grounded and validated.
    llm_result = _llm_structured_summary(text)
    if llm_result and _validate_llm_summary(llm_result, text):
        return llm_result

    short_summary = _clean_summary(short_summary, max_sentences=6)
    detailed_summary = _clean_summary(detailed_summary, max_sentences=8)

    return {
        "short_summary":    short_summary,
        "detailed_summary": detailed_summary,
        "key_points":       key_points,
    }


def summarize_judgment(text: str) -> str:
    """Return bullet-point key points string (legacy compatibility)."""
    s = summarize_structured(text)
    pts = s["key_points"]
    if isinstance(pts[0], dict):
        return "\n".join(f"• {p['label']}: {p['explanation']}" for p in pts)
    return "\n".join(f"• {p}" for p in pts)


def make_basic_summary(text: str) -> str:
    """
    Minimal plain-English summary (max 6 sentences).
    No legal jargon. Suitable for translation.
    """
    text = normalize_text(text)
    if len(text.strip()) < 80:
        return "The document does not have enough text to summarize."

    clean_text = _remove_header_noise(text)
    fact_paras     = _find_fact_paragraphs(clean_text)
    decision_paras = _find_decision_paragraphs(clean_text)
    arg_paras      = _find_argument_paragraphs(clean_text)

    sentences = []
    for p in fact_paras[:2]:
        sentences.append(_simplify(_best_sentence(p)))
    for p in arg_paras[:1]:
        sentences.append(_simplify(_best_sentence(p)))
    for p in decision_paras[:2]:
        sentences.append(_simplify(_best_sentence(p)))

    if not sentences:
        paras = _split_paragraphs(clean_text)
        for p in paras[:3]:
            sentences.append(_simplify(_best_sentence(p)))

    if not sentences:
        return "Summary could not be generated."
    return _clean_summary(" ".join(sentences[:6]), max_sentences=6)
