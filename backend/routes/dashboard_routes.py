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


@router.get("/audit/{case_id}")
def audit_logs(case_id: str):
    conn = None
    cursor = None
    try:
        conn = get_mysql_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, case_id, rule_based_json, ai_json, final_json, learning_applied_json,
                   is_rule_valid, used_ai, confidence_score,
                   quality_gate_passed, quality_gate_reasons, sql_write_allowed,
                   created_at
            FROM case_audit_logs
            WHERE case_id = %s
            ORDER BY created_at DESC
            """,
            (case_id,),
        )
        return {"case_id": case_id, "items": cursor.fetchall() or []}
    except Exception as exc:
        return {"error": str(exc)}
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.get("/intelligence")
def intelligence():
    """
    MySQL-only aggregate analytics across eCourts + BNS + ADR.
    """
    conn = None
    cursor = None
    try:
        conn = get_mysql_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT COUNT(*) AS total_cases FROM cases")
        total_cases = (cursor.fetchone() or {}).get("total_cases", 0)

        cursor.execute("SELECT COUNT(*) AS ecourts_linked FROM ecourts_case_status")
        ecourts_linked = (cursor.fetchone() or {}).get("ecourts_linked", 0)

        cursor.execute("SELECT COUNT(*) AS deprecated_cases FROM case_section_reports WHERE has_deprecated_citations = TRUE")
        deprecated_cases = (cursor.fetchone() or {}).get("deprecated_cases", 0)

        cursor.execute("SELECT COUNT(*) AS adr_assessed FROM adr_suitability")
        adr_assessed = (cursor.fetchone() or {}).get("adr_assessed", 0)

        cursor.execute("SELECT COUNT(*) AS lok_eligible FROM adr_suitability WHERE is_lok_adalat_eligible = TRUE")
        lok_eligible = (cursor.fetchone() or {}).get("lok_eligible", 0)

        cursor.execute(
            """
            SELECT recommended_adr, COUNT(*) AS count
            FROM adr_suitability
            GROUP BY recommended_adr
            ORDER BY count DESC
            """
        )
        adr_mix = cursor.fetchall() or []

        return {
            "total_cases": total_cases,
            "ecourts_linked": ecourts_linked,
            "deprecated_citation_cases": deprecated_cases,
            "adr_assessed_cases": adr_assessed,
            "lok_adalat_eligible_cases": lok_eligible,
            "coverage": {
                "ecourts_pct": round((ecourts_linked / total_cases) * 100, 2) if total_cases else 0,
                "adr_pct": round((adr_assessed / total_cases) * 100, 2) if total_cases else 0,
                "deprecated_pct": round((deprecated_cases / total_cases) * 100, 2) if total_cases else 0,
            },
            "adr_recommendation_mix": adr_mix,
        }
    except Exception as exc:
        return {"error": str(exc)}
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.get("/case-intelligence/{case_number:path}")
def case_intelligence(case_number: str):
    """
    Combined per-case intelligence view:
    - latest eCourts status
    - BNS section mapping report
    - ADR assessment
    """
    conn = None
    cursor = None
    try:
        conn = get_mysql_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT case_number, cnr_number, case_stage, next_hearing_date, last_hearing_date,
                   judge_assigned, court_complex, source, last_synced_at
            FROM ecourts_case_status
            WHERE case_number = %s
            ORDER BY last_synced_at DESC
            LIMIT 1
            """,
            (case_number,),
        )
        ecourts = cursor.fetchone()

        cursor.execute(
            """
            SELECT case_number, total_citations, unique_sections, deprecated_count, unmapped_count,
                   document_era, has_deprecated_citations, citation_quality_score, created_at
            FROM case_section_reports
            WHERE case_number = %s
            LIMIT 1
            """,
            (case_number,),
        )
        bns_report = cursor.fetchone()

        cursor.execute(
            """
            SELECT case_number, case_type, lok_adalat_score, mediation_score, arbitration_score,
                   negotiation_score, recommended_adr, is_lok_adalat_eligible, confidence_level,
                   predicted_settlement_amount, predicted_settlement_pct, predicted_days_to_settle, assessed_at
            FROM adr_suitability
            WHERE case_number = %s
            LIMIT 1
            """,
            (case_number,),
        )
        adr = cursor.fetchone()

        return {
            "case_number": case_number,
            "ecourts": ecourts,
            "section_mapping": bns_report,
            "adr_assessment": adr,
        }
    except Exception as exc:
        return {"error": str(exc)}
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
