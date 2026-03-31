try:
    import requests
except Exception:
    requests = None

from backend.database.settings import OLLAMA_BASE_URL, OLLAMA_MODEL


def ollama_is_configured() -> bool:
    return requests is not None and bool(OLLAMA_BASE_URL) and bool(OLLAMA_MODEL)


def ollama_generate(prompt: str) -> str:
    if not ollama_is_configured():
        raise RuntimeError("Ollama client is not available")

    response = requests.post(
        f"{OLLAMA_BASE_URL.rstrip('/')}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
        },
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("response", "")
