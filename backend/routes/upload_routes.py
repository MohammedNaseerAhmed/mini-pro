from fastapi import APIRouter, UploadFile, File
import shutil, os
from datetime import datetime
import uuid

from backend.database.mongo import get_db
from backend.database.mysql import get_mysql_connection
from backend.ai.text_pipeline import detect_language_code, normalize_text, split_paragraphs
from backend.utils.ocr_processor import extract_text
from backend.services.pipeline_worker import enqueue_case

router = APIRouter(prefix="/cases", tags=["Cases"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/upload-case")
async def upload_case(file: UploadFile = File(...)):
    try:
        db = get_db()
        case_number = f"CASE-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
        file_path = os.path.join(UPLOAD_DIR, f"{case_number}_{file.filename}")

        print("STEP 1: Saving file")

        # save file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        print("STEP 2: File saved ->", file_path)

        # OCR extraction
        print("STEP 3: Starting OCR")
        extracted_text = extract_text(file_path)

        print("STEP 4: OCR DONE")
        print("TEXT LENGTH:", len(extracted_text))

        if not extracted_text or len(extracted_text.strip()) == 0:
            return {"error": "OCR returned empty text"}

        clean_text = normalize_text(extracted_text)
        paragraphs = split_paragraphs(extracted_text)
        language_code = detect_language_code(extracted_text)

        now = datetime.utcnow()
        clean_title = extracted_text.strip().split("\n")[0][:150].strip() if extracted_text.strip() else "Untitled Case"

        document = {
            "source_type": "upload",
            "case_number": case_number,
            "title": clean_title,
            "file_info": {
                "file_name": file.filename,
                "stored_path": file_path,
                "upload_time": now
            },
            "judgment_text": {
                "raw_text": extracted_text,
                "clean_text": clean_text,
                "paragraphs": paragraphs,
                "language": language_code,
                "token_count": len(clean_text.split()),
            },
            "processing_status": "cleaned",
            "nlp_flags": {
                "text_cleaned": False,
                "entities_extracted": False,
                "summarized": False,
                "translated": False,
                "classified": False,
                "embedded": False,
                "chunks_created": False,
                "prediction_done": False,
            },
            "created_at": now,
            "last_updated_at": now,
        }

        print("STEP 5: Connecting DB")
        print("DB OBJECT:", db)

        result = db["raw_judgments"].insert_one(document)
        case_id = result.inserted_id

        mysql_conn = None
        mysql_cursor = None
        try:
            mysql_conn = get_mysql_connection()
            mysql_cursor = mysql_conn.cursor()
            mysql_cursor.execute(
                """
                INSERT INTO cases (case_number, title)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE title = VALUES(title)
                """,
                (case_number, clean_title),
            )
            mysql_conn.commit()
        except Exception as mysql_err:
            print("MYSQL METADATA INSERT SKIPPED:", str(mysql_err))
        finally:
            if mysql_cursor:
                mysql_cursor.close()
            if mysql_conn:
                mysql_conn.close()

        enqueue_case(case_id=case_id, case_number=case_number, stage="extracted")

        print("STEP 6: INSERTED")

        return {
            "status": "stored",
            "case_number": case_number,
            "chars_extracted": len(extracted_text),
            "language_code": language_code,
            "paragraph_count": len(paragraphs),
            "inserted_id": str(case_id)
        }

    except Exception as e:
        print("ERROR OCCURRED:", str(e))
        return {"error": str(e)}


@router.get("/features/{case_number:path}")
def case_features(case_number: str):
    db = get_db()
    case_doc = db["raw_judgments"].find_one({"case_number": case_number})
    if not case_doc:
        return {"error": "case not found"}

    summary = db["case_summaries"].find_one({"case_number": case_number})
    translation = db["case_translations"].find_one({"case_number": case_number})
    chunks_count = db["case_chunks"].count_documents({"case_number": case_number})
    emb_count = db["embeddings_metadata"].count_documents({"case_number": case_number})
    prediction = db["case_predictions"].find_one({"case_number": case_number})

    raw_text = case_doc.get("judgment_text", {}).get("raw_text", "")
    clean_text = case_doc.get("judgment_text", {}).get("clean_text", "")
    langs = []
    if translation and translation.get("translation"):
        langs = list(translation.get("translation", {}).keys())

    return {
        "case_number": case_number,
        "ocr_extracted": bool(raw_text),
        "cleaned_text_available": bool(clean_text),
        "paragraph_count": len(case_doc.get("judgment_text", {}).get("paragraphs", [])),
        "language_code": case_doc.get("judgment_text", {}).get("language", "unknown"),
        "summary_available": bool(summary and summary.get("summary")),
        "multilanguage_available": len(langs) > 0,
        "languages": langs,
        "rag_ready": chunks_count > 0 and emb_count > 0,
        "prediction_available": bool(prediction),
        "processing_status": case_doc.get("processing_status"),
        "nlp_flags": case_doc.get("nlp_flags", {}),
    }

