from fastapi import APIRouter
from backend.ai.legal_chatbot import generate_answer
from backend.database.mysql import get_mysql_connection
from time import perf_counter

router = APIRouter(prefix="/chatbot", tags=["Legal Chatbot"])

@router.get("/ask")
def ask_question(q: str, case_number: str = None):
    """
    Ask the hybrid legal chatbot a question.

    Query params:
      q           – the user's question (required)
      case_number – optional, scope document RAG to a specific case

    Returns:
      answer            – the chatbot's response
      mode              – 'document_rag' | 'legal_knowledge' | 'hybrid' | 'none'
      retrieved_case_ids – list of case numbers used for RAG context
      response_time_ms  – latency
    """
    t0 = perf_counter()
    rag = generate_answer(q, case_number=case_number)
    answer             = rag.get("answer", "")
    retrieved_case_ids = rag.get("retrieved_case_ids", [])
    mode               = rag.get("mode", "document_rag")
    response_time_ms   = int((perf_counter() - t0) * 1000)

    conn = None
    cursor = None
    try:
        conn   = get_mysql_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO chat_history (user_query, ai_response, case_context_ids, response_time_ms)
            VALUES (%s, %s, %s, %s)
            """,
            (q, answer, ",".join(retrieved_case_ids), response_time_ms),
        )
        conn.commit()
    except Exception:
        pass
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()

    return {
        "question":          q,
        "answer":            answer,
        "mode":              mode,
        "retrieved_case_ids": retrieved_case_ids,
        "response_time_ms":  response_time_ms,
    }
