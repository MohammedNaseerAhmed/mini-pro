"""
Upload route — Legal Document ingestion pipeline.

Flow:
1. Save uploaded file
2. OCR → extract raw text
3. Normalize text → MongoDB fields
4. Zone-based metadata extraction → structured dict
5. INSERT full metadata into SQL (all cases table columns)
6. INSERT document into MongoDB (raw_text, clean_text, paragraphs, language)
7. Enqueue background pipeline worker
"""

from fastapi import APIRouter, UploadFile, File
import shutil, os
from datetime import datetime
import uuid

from backend.database.mongo import get_db
from backend.database.mysql import get_mysql_connection
from backend.ai.text_pipeline import detect_language_code, normalize_text, split_paragraphs
from backend.utils.ocr_processor import extract_text
from backend.utils.case_extractor import extract_case_metadata, validate_metadata_for_sql
from backend.services.pipeline_worker import enqueue_case

router = APIRouter(prefix="/cases", tags=["Cases"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _v(val):
    """Return None if val is None/empty/'unknown', else return val."""
    if val is None:
        return None
    s = str(val).strip()
    return None if (not s or s.lower() == "unknown") else s


def _upsert_case_sql(case_number: str, meta: dict, file_path: str) -> int | None:
    """
    Insert or update the cases row with all extracted metadata.
    Never inserts raw document text into SQL.
    Rejects insert if case_number looks like an internal placeholder (no real case detected).
    Returns internal case_id on success, None on error or rejection.
    """
    # Guard: do not insert if no real case number was detected
    if not case_number or case_number.startswith("CASE-"):
        print(f"[upload] SQL insert skipped — no real case_number detected ({case_number})")
        return None

    conn = None
    cursor = None
    try:
        conn = get_mysql_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO cases (
                case_number, title, court_name, court_level, bench,
                case_type, filing_date, registration_date, decision_date,
                petitioner, respondent, judge_names, advocates,
                disposition, citation, source, pdf_url
            )
            VALUES (%s, %s, %s, %s, %s,  %s, %s, %s, %s,  %s, %s, %s, %s,  %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                title              = VALUES(title),
                court_name         = COALESCE(VALUES(court_name),        court_name),
                court_level        = COALESCE(VALUES(court_level),        court_level),
                bench              = COALESCE(VALUES(bench),              bench),
                case_type          = COALESCE(VALUES(case_type),          case_type),
                filing_date        = COALESCE(VALUES(filing_date),        filing_date),
                registration_date  = COALESCE(VALUES(registration_date),  registration_date),
                decision_date      = COALESCE(VALUES(decision_date),      decision_date),
                petitioner         = COALESCE(VALUES(petitioner),         petitioner),
                respondent         = COALESCE(VALUES(respondent),         respondent),
                judge_names        = COALESCE(VALUES(judge_names),        judge_names),
                advocates          = COALESCE(VALUES(advocates),          advocates),
                disposition        = COALESCE(VALUES(disposition),        disposition),
                citation           = COALESCE(VALUES(citation),           citation),
                pdf_url            = COALESCE(VALUES(pdf_url),            pdf_url)
            """,
            (
                case_number,
                _v(meta.get("title")),
                _v(meta.get("court_name")),
                _v(meta.get("court_level")),
                _v(meta.get("bench")),
                _v(meta.get("case_type")),
                _v(meta.get("filing_date")),
                _v(meta.get("registration_date")),
                _v(meta.get("decision_date")),
                _v(meta.get("petitioner")),
                _v(meta.get("respondent")),
                _v(meta.get("judge_names")),
                _v(meta.get("advocates")),
                _v(meta.get("disposition")),
                _v(meta.get("citation")),
                "upload",             # source
                file_path,            # pdf_url (local path)
            ),
        )
        conn.commit()

        # Fetch the auto-assigned case_id
        cursor.execute("SELECT case_id FROM cases WHERE case_number = %s", (case_number,))
        row = cursor.fetchone()
        return int(row[0]) if row else None

    except Exception as exc:
        print(f"[upload] SQL insert error: {exc}")
        return None
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.post("/upload-case")
async def upload_case(file: UploadFile = File(...)):
    try:
        db = get_db()

        # ── Step 1: Generate internal case number & save file ──────────────
        internal_case_number = (
            f"CASE-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
        )
        file_path = os.path.join(UPLOAD_DIR, f"{internal_case_number}_{file.filename}")
        print(f"[upload] Saving file → {file_path}")
        with open(file_path, "wb") as buf:
            shutil.copyfileobj(file.file, buf)

        # ── Step 2: OCR ────────────────────────────────────────────────────
        print("[upload] Running OCR …")
        extracted_text = extract_text(file_path)
        print(f"[upload] OCR done — {len(extracted_text)} chars")

        if not extracted_text or not extracted_text.strip():
            return {"error": "OCR returned empty text"}

        # ── Step 3: Text normalization ─────────────────────────────────────
        clean_text    = normalize_text(extracted_text)
        paragraphs    = split_paragraphs(extracted_text)
        language_code = detect_language_code(extracted_text)

        # ── Step 4: Zone-based metadata extraction ─────────────────────────
        print("[upload] Extracting metadata …")
        meta = extract_case_metadata(extracted_text)

        # Use extracted case number if confidently found, else keep internal
        extracted_cn = meta.get("case_number")
        case_number = extracted_cn if extracted_cn else internal_case_number
        meta["source"]  = "upload"
        meta["pdf_url"] = file_path

        # ── Build title: ONLY from parties — never from raw OCR first-line ──
        p = _v(meta.get("petitioner"))
        r = _v(meta.get("respondent"))
        if p and r:
            title = f"{p} vs {r}"
        elif p:
            title = p
        elif r:
            title = r
        else:
            title = extracted_cn or internal_case_number  # fallback to case number
        meta["title"] = title  # ensure consistent title everywhere

        now = datetime.utcnow()

        # ── Step 5: Store in MongoDB (full document) ───────────────────────
        # MongoDB gets ALL raw text fields. SQL gets ONLY structured metadata.
        document = {
            "source_type": "upload",
            "case_number": case_number,
            "title": title,
            "file_info": {
                "file_name":   file.filename,
                "stored_path": file_path,
                "upload_time": now,
            },
            # Full text lives ONLY in MongoDB
            "judgment_text": {
                "raw_text":    extracted_text,
                "clean_text":  clean_text,
                "paragraphs":  paragraphs,
                "language":    language_code,
                "token_count": len(clean_text.split()),
            },
            # Structured metadata also mirrored here for chatbot/RAG queries
            "case_metadata": meta,
            "processing_status": "cleaned",
            "nlp_flags": {
                "text_cleaned":       True,
                "entities_extracted": bool(meta.get("petitioner") or meta.get("judge_names")),
                "summarized":         False,
                "translated":         False,
                "classified":         False,
                "embedded":           False,
                "chunks_created":     False,
                "prediction_done":    False,
            },
            "created_at":      now,
            "last_updated_at": now,
        }

        result  = db["raw_judgments"].insert_one(document)
        case_id = result.inserted_id
        print(f"[upload] MongoDB inserted → {case_id}")

        # ── Step 6: Validate + Insert full metadata into SQL ──────────────
        # Validation: reject rows that fail mandatory field rules
        print("[upload] Validating metadata for SQL …")
        is_valid, rejection_reason = validate_metadata_for_sql(meta)
        if not is_valid:
            print(f"[upload] SQL insert REJECTED — {rejection_reason}")
            case_id_mysql = None
        else:
            # SQL stores ONLY structured columns — never raw text
            print("[upload] Inserting SQL metadata …")
            case_id_mysql = _upsert_case_sql(case_number, meta, file_path)
        if case_id_mysql:
            # Back-link MySQL ID into the MongoDB document
            db["raw_judgments"].update_one(
                {"_id": case_id},
                {"$set": {"case_id_mysql": case_id_mysql}},
            )
            print(f"[upload] SQL inserted → case_id={case_id_mysql}")
        else:
            print("[upload] SQL insert skipped (error or duplicate)")

        # ── Step 7: Enqueue background pipeline ───────────────────────────
        enqueue_case(case_id=case_id, case_number=case_number, stage="extracted")
        print("[upload] Enqueued pipeline worker")

        return {
            "status":          "stored",
            "case_number":     case_number,
            "chars_extracted": len(extracted_text),
            "language_code":   language_code,
            "paragraph_count": len(paragraphs),
            "inserted_id":     str(case_id),
            "sql_case_id":     case_id_mysql,
            "case_metadata":   {k: v for k, v in meta.items() if v is not None},
        }

    except Exception as e:
        print(f"[upload] ERROR: {e}")
        return {"error": str(e)}


@router.get("/features/{case_number:path}")
def case_features(case_number: str):
    db = get_db()
    case_doc = db["raw_judgments"].find_one({"case_number": case_number})
    if not case_doc:
        return {"error": "case not found"}

    summary     = db["case_summaries"].find_one({"case_number": case_number})
    translation = db["case_translations"].find_one({"case_number": case_number})
    chunks_count = db["case_chunks"].count_documents({"case_number": case_number})
    emb_count    = db["embeddings_metadata"].count_documents({"case_number": case_number})
    prediction   = db["case_predictions"].find_one({"case_number": case_number})

    raw_text   = case_doc.get("judgment_text", {}).get("raw_text", "")
    clean_text = case_doc.get("judgment_text", {}).get("clean_text", "")
    langs = []
    if translation and translation.get("translation"):
        langs = list(translation.get("translation", {}).keys())

    return {
        "case_number":             case_number,
        "ocr_extracted":           bool(raw_text),
        "cleaned_text_available":  bool(clean_text),
        "paragraph_count":         len(case_doc.get("judgment_text", {}).get("paragraphs", [])),
        "language_code":           case_doc.get("judgment_text", {}).get("language", "unknown"),
        "summary_available":       bool(summary and summary.get("summary")),
        "multilanguage_available": len(langs) > 0,
        "languages":               langs,
        "rag_ready":               chunks_count > 0 and emb_count > 0,
        "prediction_available":    bool(prediction),
        "processing_status":       case_doc.get("processing_status"),
        "nlp_flags":               case_doc.get("nlp_flags", {}),
        "case_metadata":           case_doc.get("case_metadata", {}),
    }
