import os
import re
from typing import List, Tuple

from backend.ai.translator import translate_text
from backend.ai.vector_store import vector_store
from backend.database.mongo import get_db

MODEL_NAME = "google/flan-t5-base"
_tokenizer = None
_model = None
_load_error = None


def _load_model_once() -> bool:
    global _tokenizer, _model, _load_error
    if _tokenizer is not None and _model is not None:
        return True
    if _load_error is not None:
        return False
    if os.getenv("LEGAL_AI_ENABLE_HEAVY_MODELS", "0") != "1":
        _load_error = "heavy models disabled"
        return False
    try:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        _model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)
        return True
    except Exception as exc:
        _load_error = str(exc)
        return False


def _lexical_retrieve_case_chunks(question: str, k: int = 5) -> List[Tuple[str, str]]:
    db = get_db()
    token_re = re.compile(r"[a-zA-Z]{3,}")
    q_tokens = set(token_re.findall((question or "").lower()))
    if not q_tokens:
        return []

    chunks = list(db["case_chunks"].find({}, {"case_number": 1, "text": 1}).limit(3000))
    scored = []
    for chunk in chunks:
        text = (chunk.get("text") or "").lower()
        case_number = chunk.get("case_number")
        if not text or not case_number:
            continue
        c_tokens = set(token_re.findall(text))
        inter = len(q_tokens & c_tokens)
        if inter == 0:
            continue
        score = inter / max(1, len(q_tokens | c_tokens))
        scored.append((score, case_number, chunk.get("text", "")))

    top = sorted(scored, key=lambda x: x[0], reverse=True)[:k]
    return [(case_number, text) for _, case_number, text in top]


def _vector_retrieve_context(question: str, k: int = 4) -> List[Tuple[str, str]]:
    db = get_db()
    contexts: List[Tuple[str, str]] = []
    for case_number in vector_store.search(question, k=k):
        case = db["raw_judgments"].find_one({"case_number": case_number})
        if not case:
            continue
        text = case.get("judgment_text", {}).get("clean_text") or case.get("judgment_text", {}).get("raw_text", "")
        if text:
            contexts.append((case_number, text[:1400]))
    return contexts


def _summary_bullets(text: str) -> str:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    points = sentences[:8] if len(sentences) >= 8 else sentences[:6]
    if not points:
        points = [text[:300] if text else "No sufficient context found."]
    return "\n".join([f"- {p}" for p in points])


def generate_answer(question: str):
    question = (question or "").strip()
    if not question:
        return {"answer": "Please provide a legal question.", "retrieved_case_ids": []}

    q_lower = question.lower()
    contexts = _vector_retrieve_context(question, k=4)
    if not contexts:
        contexts = _lexical_retrieve_case_chunks(question, k=6)

    case_ids = [case_number for case_number, _ in contexts]
    context_text = "\n\n".join([f"[Case: {c}]\n{t}" for c, t in contexts]) if contexts else "No relevant case context found."

    if any(k in q_lower for k in ["summary", "summarize", "key points", "gist"]):
        return {"answer": _summary_bullets(context_text), "retrieved_case_ids": case_ids}

    if "translate" in q_lower or "translation" in q_lower:
        target = "hi"
        if "telugu" in q_lower:
            target = "te"
        elif "hindi" in q_lower:
            target = "hi"
        elif "urdu" in q_lower:
            target = "ur"
        elif "simple english" in q_lower:
            target = "simple_en"
        translated = translate_text(context_text[:1800], [target]).get(target, context_text[:1200])
        return {"answer": translated, "retrieved_case_ids": case_ids}

    if not _load_model_once():
        facts = _summary_bullets(context_text)
        fallback_answer = (
            "Legal Expert View (RAG Fallback)\n"
            "Based on retrieved precedents, relevant points are:\n"
            f"{facts}\n"
            "Suggested legal direction: verify section applicability and procedural compliance before filing."
        )
        return {"answer": fallback_answer, "retrieved_case_ids": case_ids}

    prompt = f"""
You are a legal expert assistant.
Answer using only retrieved case context and include relevant case numbers.

Question:
{question}

Retrieved Context:
{context_text}

Answer:
"""
    inputs = _tokenizer(prompt, return_tensors="pt", truncation=True, max_length=1024)
    outputs = _model.generate(**inputs, max_length=280, temperature=0.2)
    answer = _tokenizer.decode(outputs[0], skip_special_tokens=True)
    return {"answer": answer, "retrieved_case_ids": case_ids}
