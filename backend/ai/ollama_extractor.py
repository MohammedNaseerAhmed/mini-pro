import json
import re
from typing import Dict, Optional

from backend.ai.ollama_client import ollama_generate, ollama_is_configured
from backend.ai.prompt_builder import METADATA_FIELDS, build_metadata_prompt


def _extract_json_block(text: str) -> Optional[dict]:
    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"(\{.*\})", text or "", re.DOTALL)
    if not match:
        return None

    try:
        return json.loads(match.group(1))
    except Exception:
        return None


def extract_with_ollama(text: str) -> Optional[Dict[str, Optional[str]]]:
    if not ollama_is_configured():
        return None

    prompt = build_metadata_prompt(text)
    try:
        response = ollama_generate(prompt)
        parsed = _extract_json_block(response)
        if not isinstance(parsed, dict):
            return None
        return {field: parsed.get(field) for field in METADATA_FIELDS}
    except Exception:
        return None
