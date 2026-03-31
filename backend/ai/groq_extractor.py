import json
import re
from typing import Dict, Optional

from backend.ai.groq_client import groq_generate, groq_is_configured
from backend.ai.prompt_builder import METADATA_FIELDS, build_metadata_prompt


def _extract_json_block(text: str) -> Optional[dict]:
    text = (text or "").strip()
    if not text:
        return None

    try:
        return json.loads(text)
    except Exception:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except Exception:
            pass

    inline = re.search(r"(\{.*\})", text, re.DOTALL)
    if not inline:
        return None
    try:
        return json.loads(inline.group(1))
    except Exception:
        return None


def extract_with_groq(text: str) -> Optional[Dict[str, Optional[str]]]:
    if not groq_is_configured():
        return None

    try:
        response = groq_generate(build_metadata_prompt(text))
        parsed = _extract_json_block(response)
        if not isinstance(parsed, dict):
            return None
        return {field: parsed.get(field) for field in METADATA_FIELDS}
    except Exception:
        return None
