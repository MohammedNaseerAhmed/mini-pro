from fastapi import APIRouter
from backend.database.mongo import get_db
from backend.database.mysql import get_mysql_connection
from backend.ai.predictor import predict_case_with_history
from backend.ai.summarizer import summarize_structured
from backend.ai.translator import translate_text
from backend.routes.similarity_routes import find_similar_cases

router = APIRouter(prefix="/ai", tags=["AI"])


@router.get("/summarize/{case_number:path}")
def summarize_case(case_number: str):
    db = get_db()
    case = db["raw_judgments"].find_one({"case_number": case_number})

    if not case:
        return {"error": "Case not found"}

    text = case.get("judgment_text", {}).get("raw_text", "")
    structured = summarize_structured(text)
    summary = "\n".join([f"- {p}" for p in structured.get("key_points", [])])
    case_id = str(case.get("_id"))
    case_id_mysql = case.get("case_id_mysql")

    db["case_summaries"].update_one(
        {"case_id": case_id},
        {
            "$set": {
                "case_id": case_id,
                "case_number": case_number,
                "summary": summary,
                "short_summary": structured.get("short_summary"),
                "detailed_summary": structured.get("detailed_summary"),
                "key_points": structured.get("key_points"),
            }
        },
        upsert=True,
    )

    if case_id_mysql:
        conn = None
        cursor = None
        try:
            conn = get_mysql_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM case_summaries WHERE case_id=%s", (case_id_mysql,))
            cursor.execute(
                """
                INSERT INTO case_summaries (case_id, summary_type, summary_text, model_used)
                VALUES (%s, %s, %s, %s)
                """,
                (case_id_mysql, "judgment", summary, "bart-large-cnn-or-fallback"),
            )
            conn.commit()
        except Exception:
            pass
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    return {"case_number": case_number, "summary": structured}


@router.get("/translate/{case_number:path}")
def translate_case(case_number: str, language: str = "hi"):
    db = get_db()
    case = db["raw_judgments"].find_one({"case_number": case_number})
    if not case:
        return {"error": "Case not found"}

    text = case.get("judgment_text", {}).get("clean_text") or case.get("judgment_text", {}).get("raw_text", "")
    if not text:
        return {"error": "No text found in case"}

    translated = translate_text(text, [language], source_language=case.get("judgment_text", {}).get("language"))
    selected = translated.get(language, {"translated_text": text, "model_used": "fallback-rule"})
    output = selected.get("translated_text", text)

    db["case_translations"].update_one(
        {"case_number": case_number},
        {"$set": {"case_number": case_number, "translation": {language: selected}}},
        upsert=True,
    )
    return {
        "case_number": case_number,
        "translation_language": language,
        "translated_text": output,
        "model_used": selected.get("model_used", "fallback-rule"),
    }


@router.get("/analyze/{case_number:path}")
def full_case_analysis(case_number: str, language: str = "en"):
    db = get_db()
    case = db["raw_judgments"].find_one({"case_number": case_number})
    if not case:
        return {"error": "Case not found"}

    text = case.get("judgment_text", {}).get("clean_text") or case.get("judgment_text", {}).get("raw_text", "")
    summaries = summarize_structured(text)
    translation_map = translate_text(text, [language], source_language=case.get("judgment_text", {}).get("language"))
    tsel = translation_map.get(language, {"translated_text": text, "model_used": "fallback-rule"})
    similar = find_similar_cases(case_number, top_k=5)
    similar_cases = similar.get("similar_cases", []) if isinstance(similar, dict) else []
    pred = predict_case_with_history(text)

    factors = [
        f"Language: {case.get('judgment_text', {}).get('language', 'unknown')}",
        f"Token count: {case.get('judgment_text', {}).get('token_count', 0)}",
        f"Similar cases considered: {len(similar_cases)}",
    ]

    return {
        "translation": {
            "language": language,
            "text": tsel.get("translated_text", text),
            "model_used": tsel.get("model_used", "fallback-rule"),
        },
        "summaries": {
            "short": summaries.get("short_summary", ""),
            "detailed": summaries.get("detailed_summary", ""),
            "key_points": summaries.get("key_points", []),
        },
        "similar_cases": similar_cases,
        "prediction": {
            "outcome": pred.get("prediction"),
            "probability": pred.get("confidence"),
            "confidence": pred.get("confidence"),
            "factors": pred.get("important_factors", factors),
        },
    }
