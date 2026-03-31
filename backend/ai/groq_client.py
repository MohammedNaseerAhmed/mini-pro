from typing import Optional

try:
    import requests
except Exception:
    requests = None

from backend.database.settings import GROQ_API_KEY, GROQ_MODEL


def groq_is_configured() -> bool:
    return bool(requests is not None and GROQ_API_KEY and GROQ_MODEL)


def groq_generate(prompt: str, system_prompt: Optional[str] = None) -> str:
    if not groq_is_configured():
        raise RuntimeError("Groq client is not configured")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": GROQ_MODEL,
            "messages": messages,
            "temperature": 0.1,
        },
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    choices = payload.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return (message.get("content") or "").strip()
