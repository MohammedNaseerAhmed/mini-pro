import re
from typing import Dict, List, Optional, Tuple

SUPPORTED_LANGUAGES = {
    "en": "English",
    "hi": "Hindi",
    "te": "Telugu",
    "ur": "Urdu",
    "simple_en": "Simple English",
}

_MODEL_BY_LANG = {
    "hi": "Helsinki-NLP/opus-mt-en-hi",
    "te": "Helsinki-NLP/opus-mt-en-mul",
    "ur": "Helsinki-NLP/opus-mt-en-ur",
}

_cache: Dict[str, object] = {}
_load_errors: Dict[str, str] = {}


def _protect_legal_terms(text: str) -> Tuple[str, Dict[str, str]]:
    protected = {}
    patterns = [
        r"\b(?:IPC|CrPC|CPC|FIR|PMLA|NDPS|Constitution)\b",
        r"\b(?:Section|Sec\.?|Article)\s+\d+[A-Za-z\-]*\b",
        r"\b[A-Z]{2,}[A-Z0-9\-]*\b",
    ]
    idx = 0
    out = text
    for pat in patterns:
        for m in re.finditer(pat, out, flags=re.IGNORECASE):
            term = m.group(0)
            if term in protected.values():
                continue
            token = f"__LEGAL_{idx}__"
            out = out.replace(term, token, 1)
            protected[token] = term
            idx += 1
    return out, protected


def _restore_legal_terms(text: str, protected: Dict[str, str]) -> str:
    out = text
    for token, term in protected.items():
        out = out.replace(token, term)
    return out


def _load_translation_pipeline(lang_code: str):
    if lang_code in _cache:
        return _cache[lang_code]
    if lang_code in _load_errors:
        return None
    try:
        from transformers import pipeline

        model_name = _MODEL_BY_LANG.get(lang_code)
        if not model_name:
            _load_errors[lang_code] = "unsupported language model"
            return None
        p = pipeline("translation", model=model_name)
        _cache[lang_code] = p
        return p
    except Exception as exc:
        _load_errors[lang_code] = str(exc)
        return None


def _fallback_translate(text: str, lang: str) -> str:
    # Lightweight fallback to avoid returning empty content when model is unavailable.
    if lang == "simple_en":
        sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        return " ".join(sents[:8]) if sents else text
    prefix = {"hi": "[Hindi]", "te": "[Telugu]", "ur": "[Urdu]", "en": "[English]"}.get(lang, "[Translated]")
    return f"{prefix} {text}"


def translate_text(
    text: str, target_languages: Optional[List[str]] = None, source_language: Optional[str] = None
) -> Dict[str, Dict[str, str]]:
    text = (text or "").strip()
    if not text:
        return {}

    langs = target_languages or ["hi"]
    protected_text, protected_terms = _protect_legal_terms(text)
    outputs: Dict[str, Dict[str, str]] = {}

    for lang in langs:
        lang = lang.lower()
        if lang not in SUPPORTED_LANGUAGES:
            continue
        if lang in {"en", "simple_en"}:
            translated = _fallback_translate(protected_text, lang)
            translated = _restore_legal_terms(translated, protected_terms)
            outputs[lang] = {"translated_text": translated, "model_used": "rule-based"}
            continue

        pipe = _load_translation_pipeline(lang)
        if pipe is None:
            translated = _fallback_translate(protected_text, lang)
            translated = _restore_legal_terms(translated, protected_terms)
            outputs[lang] = {"translated_text": translated, "model_used": "fallback-rule"}
            continue

        try:
            chunk = protected_text[:2500]
            result = pipe(chunk, max_length=700)
            translated = result[0]["translation_text"] if result else chunk
            translated = _restore_legal_terms(translated, protected_terms)
            outputs[lang] = {"translated_text": translated, "model_used": _MODEL_BY_LANG.get(lang, "unknown")}
        except Exception:
            translated = _fallback_translate(protected_text, lang)
            translated = _restore_legal_terms(translated, protected_terms)
            outputs[lang] = {"translated_text": translated, "model_used": "fallback-rule"}

    return outputs
