METADATA_FIELDS = [
    "case_number",
    "case_prefix",
    "case_number_numeric",
    "case_year",
    "petitioner",
    "respondent",
    "judge_names",
    "disposition",
    "court_name",
    "court_level",
    "case_type",
    "decision_date",
    "citation",
]


def build_metadata_prompt(text: str) -> str:
    return (
        "You are a legal AI system.\n\n"
        "Extract structured data from the judgment.\n\n"
        "STRICT RULES:\n"
        "- Return ONLY JSON\n"
        "- No hallucination\n"
        "- If missing, use null\n"
        "- Preserve names, section numbers, and case identifiers exactly\n\n"
        "Fields:\n"
        + ", ".join(METADATA_FIELDS)
        + "\n\nTEXT:\n"
        + (text or "")[:6000]
    )


def _format_history(chat_history: list = None) -> str:
    if not chat_history:
        return ""
    history_lines = []
    for msg in chat_history[-8:]:
        if not isinstance(msg, dict):
            continue
        text = str(msg.get("text", "")).strip()
        if not text:
            continue
        role = str(msg.get("role", "assistant")).strip().lower()
        speaker = "User" if role == "user" else "Assistant"
        history_lines.append(f"{speaker}: {text}")

    if not history_lines:
        return ""

    return "Conversation history:\n" + "\n".join(history_lines) + "\n\n"

def build_chat_prompt(question: str, context: str, chat_history: list = None) -> str:
    history_text = _format_history(chat_history)
    return (
        "You are a legal assistant answering questions about court documents.\n"
        "Use only the provided context when answering.\n"
        "If the answer is not supported by the context, say so clearly.\n"
        "Keep the answer concise, factual, and easy to audit.\n\n"
        f"Context:\n{context[:8000]}\n\n"
        f"{history_text}"
        f"Current user question:\n{question}"
    )


def _build_general_legal_prompt(question: str, chat_history: list = None) -> str:
    history_text = _format_history(chat_history)
    return (
        "You are an Indian legal assistant.\n"
        "Answer the user's general legal question clearly and accurately.\n"
        "Rules:\n"
        "- Do not say 'not mentioned in document' for general legal questions.\n"
        "- If uncertain, say what is generally true and suggest consulting a lawyer.\n"
        "- Keep response concise, structured, and practical.\n"
        "- Prefer Indian legal context when relevant.\n\n"
        f"{history_text}"
        f"Current user question:\n{question}"
    )
