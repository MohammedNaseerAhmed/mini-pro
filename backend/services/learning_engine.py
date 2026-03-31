from difflib import SequenceMatcher
from typing import Dict, List, Optional

from backend.database.mysql import get_mysql_connection

LEARNING_FIELDS = {
    "case_number",
    "title",
    "court_name",
    "court_level",
    "bench",
    "case_type",
    "case_year",
    "filing_date",
    "registration_date",
    "decision_date",
    "petitioner",
    "respondent",
    "judge_names",
    "advocates",
    "disposition",
    "citation",
}


def _normalize(value: Optional[str]) -> str:
    if value is None:
        return ""
    return str(value).strip()


def similar(a: Optional[str], b: Optional[str]) -> float:
    left = _normalize(a).lower()
    right = _normalize(b).lower()
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def get_recent_feedback(limit: int = 1000) -> List[Dict[str, str]]:
    conn = None
    cursor = None
    try:
        conn = get_mysql_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT case_id, field_name, predicted_value, corrected_value, source, created_at
            FROM learning_feedback
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return cursor.fetchall() or []
    except Exception:
        return []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def apply_learning(meta: Dict[str, Optional[str]], similarity_threshold: float = 0.88) -> Dict[str, object]:
    updated = dict(meta)
    applied_rules: List[Dict[str, object]] = []

    for feedback in get_recent_feedback():
        field = (feedback.get("field_name") or "").strip()
        if field not in LEARNING_FIELDS:
            continue

        current_value = updated.get(field)
        predicted_value = feedback.get("predicted_value")
        corrected_value = feedback.get("corrected_value")
        if not current_value or not predicted_value or not corrected_value:
            continue

        score = similar(current_value, predicted_value)
        if score < similarity_threshold:
            continue

        updated[field] = corrected_value
        applied_rules.append(
            {
                "field_name": field,
                "matched_value": current_value,
                "predicted_value": predicted_value,
                "corrected_value": corrected_value,
                "similarity": round(score, 4),
                "source": feedback.get("source"),
            }
        )

    return {
        "metadata": updated,
        "applied_rules": applied_rules,
    }
