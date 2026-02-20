from fastapi import APIRouter

from backend.database.mongo import get_db
from backend.database.mysql import get_mysql_connection

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/overview")
def overview():
    db = get_db()
    total_cases = db["raw_judgments"].count_documents({})
    total_completed = db["processing_queue"].count_documents({"status": "completed"})
    total_failed = db["processing_queue"].count_documents({"status": "failed"})
    total_pending = db["processing_queue"].count_documents({"status": {"$in": ["pending", "retry", "processing"]}})

    return {
        "total_cases": total_cases,
        "completed": total_completed,
        "failed": total_failed,
        "pending_or_processing": total_pending,
    }


@router.get("/metrics")
def metrics():
    db = get_db()
    total = db["raw_judgments"].count_documents({})
    summaries = db["case_summaries"].count_documents({})
    translations = db["case_translations"].count_documents({})
    chunks = db["case_chunks"].count_documents({})
    embeddings = db["embeddings_metadata"].count_documents({})
    predictions = db["case_predictions"].count_documents({})
    return {
        "total_cases": total,
        "summary_coverage_pct": round((summaries / total) * 100, 2) if total else 0,
        "translation_coverage_pct": round((translations / total) * 100, 2) if total else 0,
        "rag_coverage_pct": round((min(chunks, embeddings) / total) * 100, 2) if total else 0,
        "prediction_coverage_pct": round((predictions / total) * 100, 2) if total else 0,
    }


@router.get("/recent-activity")
def recent_activity(limit: int = 20):
    db = get_db()
    logs = list(
        db["ai_outputs"]
        .find({}, {"_id": 0, "case_number": 1, "stage": 1, "created_at": 1})
        .sort("created_at", -1)
        .limit(max(1, min(limit, 100)))
    )
    return {"events": logs}


@router.get("/cases")
def list_cases(limit: int = 20):
    db = get_db()
    cursor = db["raw_judgments"].find({}, {"case_number": 1, "title": 1, "processing_status": 1, "created_at": 1}).sort(
        "created_at", -1
    )
    rows = []
    for doc in cursor.limit(max(1, min(limit, 200))):
        rows.append(
            {
                "case_number": doc.get("case_number"),
                "title": doc.get("title"),
                "processing_status": doc.get("processing_status"),
                "created_at": doc.get("created_at"),
            }
        )
    return {"cases": rows}


@router.get("/pipeline/{case_number}")
def pipeline_status(case_number: str):
    db = get_db()
    queue = db["processing_queue"].find_one({"case_number": case_number}, {"_id": 0})
    case_doc = db["raw_judgments"].find_one(
        {"case_number": case_number},
        {"_id": 0, "processing_status": 1, "nlp_flags": 1, "case_id_mysql": 1},
    )
    return {"case_number": case_number, "queue": queue, "case": case_doc}


@router.get("/sql-health")
def sql_health():
    conn = None
    cursor = None
    try:
        conn = get_mysql_connection()
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES")
        tables = [row[0] for row in cursor.fetchall()]
        return {"ok": True, "tables": tables}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
