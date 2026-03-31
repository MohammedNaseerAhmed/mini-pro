from typing import Literal

from pydantic import BaseModel, Field
from fastapi import APIRouter

from backend.database.mysql import get_mysql_connection

router = APIRouter(prefix="/feedback", tags=["Feedback"])


class FeedbackPayload(BaseModel):
    case_id: str = Field(..., min_length=1)
    field: str = Field(..., min_length=1, max_length=50)
    predicted: str = Field(..., min_length=1)
    corrected: str = Field(..., min_length=1)
    source: Literal["rule", "ai", "final", "manual"] = "manual"


@router.post("")
def store_feedback(data: FeedbackPayload):
    conn = None
    cursor = None
    try:
        conn = get_mysql_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO learning_feedback (
                case_id,
                field_name,
                predicted_value,
                corrected_value,
                source
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (data.case_id, data.field, data.predicted, data.corrected, data.source),
        )
        conn.commit()
        return {"status": "stored", "field": data.field, "case_id": data.case_id}
    except Exception as exc:
        return {"error": str(exc)}
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.get("")
def list_feedback(limit: int = 50):
    conn = None
    cursor = None
    try:
        conn = get_mysql_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, case_id, field_name, predicted_value, corrected_value, source, created_at
            FROM learning_feedback
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (max(1, min(limit, 200)),),
        )
        return {"items": cursor.fetchall() or []}
    except Exception as exc:
        return {"error": str(exc)}
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
