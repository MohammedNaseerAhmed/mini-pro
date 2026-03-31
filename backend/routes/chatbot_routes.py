from time import perf_counter
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from backend.ai.legal_chatbot import generate_answer
from backend.ai.translator import LANGUAGE_NAMES, translate_for_chatbot
from backend.database.mongo import get_db
from backend.database.mysql import get_mysql_connection

router = APIRouter(prefix="/chatbot", tags=["Legal Chatbot"])


class ChatMessage(BaseModel):
    role: str
    text: str


class ChatRequest(BaseModel):
    query: str
    case_number: Optional[str] = None
    language: str = "en"
    response_mode: str = "auto"
    chat_history: Optional[List[ChatMessage]] = None


@router.post("/ask")
def ask_question(req: ChatRequest):
    """
    Ask the hybrid legal chatbot a question.

    Body:
      query         - the user's question (required)
      case_number   - optional, scope document RAG to a specific case
      chat_history  - optional previous messages
      language      - optional output language
      response_mode - optional: auto | hybrid | rag | general | metadata
    """
    t0 = perf_counter()

    chat_history = []
    if req.chat_history:
        chat_history = [{"role": msg.role, "text": msg.text} for msg in req.chat_history]

    rag = generate_answer(
        req.query,
        case_number=req.case_number,
        response_mode=req.response_mode,
        chat_history=chat_history,
    )
    answer = rag.get("answer", "")
    retrieved_case_ids = rag.get("retrieved_case_ids", [])
    mode = rag.get("mode", "document_rag")

    language_req = (req.language or "en").lower().strip()
    if language_req not in LANGUAGE_NAMES:
        language_req = "en"

    translated = None
    if language_req != "en" and answer:
        case_meta = {}
        if req.case_number:
            db = get_db()
            doc = db["raw_judgments"].find_one({"case_number": req.case_number}, {"case_metadata": 1})
            case_meta = (doc or {}).get("case_metadata", {})
        translated = translate_for_chatbot(answer, language_req, case_metadata=case_meta)

    final_answer = translated.get("translated_text") if translated else answer
    response_time_ms = int((perf_counter() - t0) * 1000)

    conn = None
    cursor = None
    try:
        conn = get_mysql_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO chat_history (user_query, ai_response, case_context_ids, response_time_ms)
            VALUES (%s, %s, %s, %s)
            """,
            (req.query, final_answer, ",".join(retrieved_case_ids), response_time_ms),
        )
        conn.commit()
    except Exception:
        pass
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return {
        "question": req.query,
        "answer": final_answer,
        "answer_en": answer,
        "language": language_req,
        "language_name": LANGUAGE_NAMES.get(language_req, "English"),
        "translation_error": (translated or {}).get("error") if translated else None,
        "response_mode": req.response_mode,
        "mode": mode,
        "retrieved_case_ids": retrieved_case_ids,
        "response_time_ms": response_time_ms,
    }
