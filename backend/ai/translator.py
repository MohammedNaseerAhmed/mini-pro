"""
Legal AI — Multilingual Translation Module
==========================================

Spec compliance:
- Translates ONLY user-facing text (basic_summary, key_points, chatbot answers).
- NEVER translates: case numbers, party names, judge names, dates,
  section numbers, act names, legal citations.
- Pre-translation: detect legal tokens → protect with placeholders → translate → restore.
- Fallback: English text returned (never empty) if translation fails.
- Supported languages: English (en), Hindi (hi), Telugu (te).
  Extended: Kannada (kn), Tamil (ta), Malayalam (ml), Marathi (mr),
            Urdu (ur), Bengali (bn), Punjabi (pa), Gujarati (gu).
- Output format per spec: {language, translated_text, source_language}
- Cache: callers check MongoDB case_translations before calling translate.
"""

import re
from typing import Dict, List, Optional, Tuple

# ── deep-translator import (checked once at module load) ─────────────────────
try:
    from deep_translator import GoogleTranslator as _GT
    _DEEP_AVAILABLE = True
except ImportError:
    _GT = None
    _DEEP_AVAILABLE = False

# ── Supported language registry ───────────────────────────────────────────────
LANGUAGE_NAMES: Dict[str, str] = {
    "en":       "English",
    "hi":       "Hindi",
    "te":       "Telugu",
    "kn":       "Kannada",
    "ta":       "Tamil",
    "ml":       "Malayalam",
    "mr":       "Marathi",
    "ur":       "Urdu",
    "bn":       "Bengali",
    "pa":       "Punjabi",
    "gu":       "Gujarati",
    "simple_en": "Simple English",
}

# ISO 639-1 codes accepted by deep-translator / Google Translate
_DEEP_LANG: Dict[str, str] = {
    "hi": "hi", "te": "te", "kn": "kn", "ta": "ta",
    "ml": "ml", "mr": "mr", "ur": "ur", "bn": "bn",
    "pa": "pa", "gu": "gu",
}

# ─── Legal token protection patterns ─────────────────────────────────────────
# Ordered: most specific first to avoid partial matches.
_PROTECT_PATTERNS: List[str] = [
    # Section / Article / Clause / Order Rule
    r"\bSection\s+\d+[A-Za-z]?(?:\s*\(\d+\))?(?:\s+of\s+[\w\s]+?(?:Act|Code))?\b",
    r"\bSec\.\s*\d+[A-Za-z]?\b",
    r"\bArticle\s+\d+[A-Za-z]?(?:\s*\(\d+\))?\b",
    r"\bArt\.\s*\d+[A-Za-z]?\b",
    r"\bClause\s+\d+[A-Za-z]?\b",
    r"\bOrder\s+\d+\s+Rule\s+\d+\b",
    r"\bRule\s+\d+[A-Za-z]?\b",
    r"\bSchedule\s+[IVXLC]+|\bSchedule\s+\d+\b",

    # Well-known act abbreviations (standalone)
    r"\b(?:IPC|CrPC|CPC|FIR|PMLA|NDPS|POCSO|RERA|GST|RTI|RTE|FEMA|IT\s+Act)\b",

    # Full act names
    r"\b(?:NI\s+Act|Indian\s+Penal\s+Code|Code\s+of\s+Criminal\s+Procedure|"
    r"Code\s+of\s+Civil\s+Procedure|Evidence\s+Act|Indian\s+Evidence\s+Act|"
    r"Constitution(?:\s+of\s+India)?|Contract\s+Act|Indian\s+Contract\s+Act|"
    r"Transfer\s+of\s+Property\s+Act|Motor\s+Vehicles\s+Act|Limitation\s+Act|"
    r"Companies\s+Act|Insolvency\s+.{0,20}Code|Arbitration\s+.{0,20}Act|"
    r"Protection\s+of\s+Women|Domestic\s+Violence\s+Act|"
    r"Specific\s+Relief\s+Act|Registration\s+Act|Stamp\s+Act)\b",

    # Court case number formats (Indian courts)
    r"\b(?:O\.S\.|CS|CRL\.A\.|W\.P\.|C\.C\.|M\.C\.|B\.A\.|OS|WP|WPC|CWP|CC|MC|BA|"
    r"OP|O\.P\.|CMA|SA|RSA|RFA|EP|IA|CRP|TA|MA|FA|SLP|FMAT|MAT|CA|AS)\s*"
    r"(?:No\.?)?\s*\d+\s*(?:/|of)\s*\d{4}\b",

    # Internal CASE- IDs
    r"\bCASE-\d{8,}-[A-Z0-9]+\b",

    # Law reporter citations: (2021) 3 SCC 456 or AIR 2020 SC 123
    r"\(\s*(?:19|20)\d{2}\s*\)\s+\d+\s+(?:SCC|SCR|AIR|MLJ|ALT|ALR|BLR|CLR)\s+\d+",
    r"\bAIR\s+(?:19|20)\d{2}\s+(?:SC|HC|AP|Bom|Cal|Del|Ker|Mad|Raj)\s+\d+\b",

    # Dates (protect so they don't get reformatted)
    r"\b\d{1,2}[./\-]\d{1,2}[./\-](?:19|20)\d{2}\b",
    r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+(?:19|20)\d{2}\b",
]


# ─── Jargon → Simple English map ─────────────────────────────────────────────
_SIMPLE_EN: Dict[str, str] = {
    r"\bmaintainable\b":      "acceptable by the court",
    r"\bnot maintainable\b":  "may be rejected by the court",
    r"\blocus standi\b":      "legal right to file a case",
    r"\bdisposed of?\b":      "case closed / finished",
    r"\bex.?parte\b":         "without the other side present",
    r"\binter.?alia\b":       "among other things",
    r"\binjunction\b":        "court order to stop or allow something",
    r"\bstay order\b":        "temporary pause on proceedings",
    r"\bquash(?:ed)?\b":      "cancelled by the court",
    r"\bwrit\b":              "formal legal request to court",
    r"\bpetitioner\b":        "person who filed this case",
    r"\brespondent\b":        "person defending against this case",
    r"\bplaintiff\b":         "person who filed this case",
    r"\bdefendant\b":         "person defending against this case",
    r"\bapplicant\b":         "person who made this request",
    r"\badjournment\b":       "postponed to a later date",
    r"\bprima facie\b":       "based on first look / appears to be",
    r"\bjurisdiction\b":      "authority of the court",
    r"\blimitation\b":        "time limit to file a case",
    r"\baffidavit\b":         "written sworn statement",
    r"\bsubmission\b":        "argument presented in court",
    r"\bcontention\b":        "argument made in court",
    r"\bexhibit\b":           "document shown as evidence",
    r"\bdeposition\b":        "evidence given under oath",
    r"\bremand\b":            "sent back to custody",
    r"\bcognizance\b":        "formally taking up the case",
    r"\bfir\b":               "police complaint (FIR)",
    r"\bbail\b":              "temporary release from custody",
    r"\bheld\b":              "decided / ruled",
    r"\bvide\b":              "as per / referring to",
    r"\binter se\b":          "between themselves",
    r"\bopined\b":            "said / stated",
    r"\bprayed\b":            "requested from court",
}


# ═══════════════════════════════════════════════════════════════════════════════
# TOKEN PROTECTION
# ═══════════════════════════════════════════════════════════════════════════════

def _protect(text: str, extra_terms: Optional[List[str]] = None) -> Tuple[str, Dict[str, str]]:
    """
    Replace legal tokens and extra_terms (party/judge names) with __LAWn__ placeholders.

    Runs each protection pattern against the current `out` string so that
    already-replaced placeholders are never double-processed.
    Returns (protected_text, {placeholder: original_term}).
    """
    protected: Dict[str, str] = {}      # token → original term
    already_protected: set = set()       # set of original terms already replaced
    idx = 0
    out = text

    all_patterns = list(_PROTECT_PATTERNS)

    # Add caller-supplied proper nouns (party/judge names) as literal patterns
    if extra_terms:
        for term in extra_terms:
            if term and len(term.strip()) > 2:
                escaped = re.escape(term.strip())
                all_patterns.append(r"\b" + escaped + r"\b")

    for pat in all_patterns:
        try:
            # Collect all matches first, then replace (avoids index drift)
            matches = list(re.finditer(pat, out, flags=re.IGNORECASE))
            for m in matches:
                term = m.group(0)
                # Skip if this exact term string was already replaced
                if term in already_protected:
                    continue
                token = f"__LAW{idx}__"
                out = out.replace(term, token)  # replace ALL occurrences of this term
                protected[token] = term
                already_protected.add(term)
                idx += 1
        except re.error:
            pass  # skip malformed patterns

    return out, protected


def _restore(text: str, protected: Dict[str, str]) -> str:
    """Restore all __LAWn__ placeholders to their original legal terms."""
    out = text
    for token, term in protected.items():
        out = out.replace(token, term)
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# TEXT CHUNKING
# ═══════════════════════════════════════════════════════════════════════════════

def _chunk_text(text: str, max_len: int = 4500) -> List[str]:
    """
    Split text into chunks ≤ max_len chars at sentence/newline boundaries.
    Ensures each chunk is independently translatable.
    """
    if len(text) <= max_len:
        return [text]

    chunks: List[str] = []
    remaining = text.strip()
    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break
        # Prefer newline split
        cut = remaining.rfind("\n", 0, max_len)
        if cut < max_len // 3:
            # Fall back to sentence boundary
            cut = remaining.rfind(". ", 0, max_len)
        if cut < 0 or cut < max_len // 4:
            cut = max_len   # hard cut
        else:
            cut += 1        # include the period

        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()

    return [c for c in chunks if c]


# ═══════════════════════════════════════════════════════════════════════════════
# SIMPLE ENGLISH (rule-based)
# ═══════════════════════════════════════════════════════════════════════════════

def _simplify_english(text: str) -> str:
    """Replace legal jargon with plain Class-8 English equivalents."""
    out = text
    for pattern, replacement in _SIMPLE_EN.items():
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# GOOGLE TRANSLATE (via deep-translator)
# ═══════════════════════════════════════════════════════════════════════════════

def _google_translate(text: str, lang_code: str) -> Tuple[str, Optional[str]]:
    """
    Call Google Translate via deep-translator.
    Returns (translated_text, error_message_or_None).
    On any failure, returns original text with error message — never empty string.
    """
    if not _DEEP_AVAILABLE or _GT is None:
        return text, "deep-translator not installed. Run: pip install deep-translator"

    dt_code = _DEEP_LANG.get(lang_code)
    if not dt_code:
        return text, f"Language '{lang_code}' not supported for translation."

    try:
        chunks = _chunk_text(text, max_len=4500)
        translated_parts: List[str] = []
        for chunk in chunks:
            result = _GT(source="auto", target=dt_code).translate(chunk)
            translated_parts.append(result if result else chunk)
        return "\n".join(translated_parts), None
    except Exception as exc:
        return text, f"Translation failed: {exc}"


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def translate_text(
    text: str,
    target_languages: Optional[List[str]] = None,
    source_language: str = "en",
    extra_protect: Optional[List[str]] = None,
) -> Dict[str, Dict[str, str]]:
    """
    Translate user-facing text to one or more target languages.

    Args:
        text:             Text to translate (basic_summary, key_points, chatbot answer).
        target_languages: List of ISO codes, e.g. ["hi", "te"]. Defaults to ["hi"].
        source_language:  Source language code (almost always "en").
        extra_protect:    Additional proper nouns to protect (party names, judge names).
                          Extract these from case_metadata before calling.

    Returns:
        Dict keyed by language code, each value being:
        {
            "language":       "hi",
            "translated_text": "...",
            "source_language": "en",
            "model_used":     "google-translate" | "rule-based" | "english-fallback",
            "error":          None | "error message"
        }

    NEVER translates:
        - Case numbers
        - Party / judge names (pass via extra_protect)
        - Section numbers (Section 138), Act names (IPC, CrPC, NI Act)
        - Dates, legal citations
    """
    text = (text or "").strip()
    if not text:
        return {}

    langs = [lang.lower() for lang in (target_languages or ["hi"])]

    # Protect legal tokens + caller-supplied proper nouns
    protected_text, protected_map = _protect(text, extra_protect)

    outputs: Dict[str, Dict[str, str]] = {}

    for lang in langs:
        if lang not in LANGUAGE_NAMES and lang not in _DEEP_LANG:
            continue

        try:
            if lang == "simple_en":
                restored = _restore(_simplify_english(protected_text), protected_map)
                outputs[lang] = {
                    "language":        lang,
                    "translated_text": restored,
                    "source_language": source_language,
                    "model_used":      "rule-based simplification",
                    "error":           None,
                }

            elif lang == "en":
                restored = _restore(protected_text, protected_map)
                outputs[lang] = {
                    "language":        lang,
                    "translated_text": restored,
                    "source_language": source_language,
                    "model_used":      "passthrough",
                    "error":           None,
                }

            elif lang in _DEEP_LANG:
                raw_translated, error = _google_translate(protected_text, lang)
                restored = _restore(raw_translated, protected_map)

                if error:
                    # Fallback: return English text, never empty
                    outputs[lang] = {
                        "language":        lang,
                        "translated_text": text,   # original English
                        "source_language": source_language,
                        "model_used":      "english-fallback",
                        "error":           error,
                    }
                else:
                    outputs[lang] = {
                        "language":        lang,
                        "translated_text": restored,
                        "source_language": source_language,
                        "model_used":      "google-translate",
                        "error":           None,
                    }

            else:
                outputs[lang] = {
                    "language":        lang,
                    "translated_text": text,
                    "source_language": source_language,
                    "model_used":      "english-fallback",
                    "error":           f"Language '{lang}' not supported",
                }

        except Exception as exc:
            outputs[lang] = {
                "language":        lang,
                "translated_text": text,  # English fallback, never empty
                "source_language": source_language,
                "model_used":      "english-fallback",
                "error":           str(exc),
            }

    return outputs


def translate_for_chatbot(
    answer: str,
    language: str,
    case_metadata: Optional[Dict] = None,
) -> Dict[str, str]:
    """
    Translate a chatbot answer to the requested language,
    protecting party names, judge names from case_metadata.

    Returns the spec output format:
    { "language": "te", "translated_text": "...", "source_language": "en" }
    """
    if language == "en" or not language:
        return {
            "language":        "en",
            "translated_text": answer,
            "source_language": "en",
        }

    # Extract proper nouns to protect
    extra: List[str] = []
    if case_metadata:
        for field in ("petitioner", "respondent", "judge_names", "court_name"):
            val = case_metadata.get(field)
            if val and isinstance(val, str):
                # Split comma-separated judge names
                for name in val.split(","):
                    name = name.strip()
                    if len(name) > 2:
                        extra.append(name)

    result = translate_text(answer, [language], extra_protect=extra or None)
    selected = result.get(language, {})

    return {
        "language":        selected.get("language", language),
        "translated_text": selected.get("translated_text", answer),
        "source_language": "en",
        "error":           selected.get("error"),
    }
