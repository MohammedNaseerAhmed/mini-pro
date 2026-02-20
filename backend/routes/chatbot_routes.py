from fastapi import APIRouter
from backend.ai.legal_chatbot import generate_answer
from backend.database.mysql import get_mysql_connection
from time import perf_counter

router = APIRouter(prefix="/chatbot", tags=["Legal Chatbot"])

@router.get("/ask")
def ask_question(q: str):
    t0 = perf_counter()
    rag = generate_answer(q)
    answer = rag.get("answer", "")
    retrieved_case_ids = rag.get("retrieved_case_ids", [])
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
            (q, answer, ",".join(retrieved_case_ids), response_time_ms),
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
        "question": q,
        "answer": answer,
        "retrieved_case_ids": retrieved_case_ids,
        "response_time_ms": response_time_ms,
    }
