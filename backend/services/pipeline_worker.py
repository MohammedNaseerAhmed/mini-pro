import re
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from pymongo import ReturnDocument

from backend.ai.embeddings import get_embedding
from backend.ai.predictor import predict_case_with_history
from backend.ai.summarizer import summarize_structured
from backend.ai.text_pipeline import detect_language_code, normalize_text, split_paragraphs
from backend.ai.translator import translate_text
from backend.ai.vector_store import vector_store
from backend.database.mongo import get_db
from backend.database.mysql import get_mysql_connection

MAX_RETRIES = 3
WORKER_POLL_SECONDS = 2
WORKER_ID = "local-pipeline-worker"


def _utcnow() -> datetime:
    return datetime.utcnow()


def _clean_text(text: str) -> str:
    return normalize_text(text)


def _first_line_title(text: str) -> str:
    if not text:
        return "Untitled Case"
    return text.split(".")[0][:150].strip() or "Untitled Case"


def _extract_facts(clean_text: str) -> List[str]:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean_text) if s.strip()]
    return sentences[:5]


def _translate_text(clean_text: str) -> Dict[str, Dict[str, str]]:
    translated_map = translate_text(clean_text, target_languages=["en", "hi", "te"])
    if not translated_map:
        translated_map = {"en": {"translated_text": clean_text, "model_used": "fallback-rule"}}
    return translated_map


def _chunk_text(text: str, chunk_size: int = 180, overlap: int = 40) -> List[str]:
    words = text.split()
    if not words:
        return []
    chunks: List[str] = []
    step = max(1, chunk_size - overlap)
    for start in range(0, len(words), step):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(words):
            break
    return chunks


def _mysql_execute(query: str, params: tuple = (), fetchone: bool = False, fetchall: bool = False):
    conn = None
    cursor = None
    try:
        conn = get_mysql_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        row = cursor.fetchone() if fetchone else None
        rows = cursor.fetchall() if fetchall else None
        conn.commit()
        if fetchone:
            return row
        if fetchall:
            return rows
        return None
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def _log_system(module: str, action: str, details: str) -> None:
    try:
        _mysql_execute(
            """
            INSERT INTO system_logs (module, action, details)
            VALUES (%s, %s, %s)
            """,
            (module, action, details[:5000]),
        )
    except Exception:
        pass


def _get_case_id_mysql(case_number: str) -> Optional[int]:
    try:
        row = _mysql_execute(
            "SELECT case_id FROM cases WHERE case_number=%s",
            (case_number,),
            fetchone=True,
        )
        return int(row[0]) if row else None
    except Exception:
        return None


def _upsert_case_mysql(case_number: str, title: str, clean_text: str) -> Optional[int]:
    try:
        _mysql_execute(
            """
            INSERT INTO cases (case_number, title, source)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                title = VALUES(title),
                source = VALUES(source)
            """,
            (case_number, title, "upload"),
        )
        return _get_case_id_mysql(case_number)
    except Exception as exc:
        _log_system("pipeline", "sql_case_upsert_error", str(exc))
        return None


def _insert_fact_rows(case_id_mysql: int, facts: List[str]) -> None:
    if not facts:
        return
    for idx, fact in enumerate(facts, start=1):
        _mysql_execute(
            """
            INSERT INTO case_facts (case_id, fact_type, fact_text)
            VALUES (%s, %s, %s)
            """,
            (case_id_mysql, f"fact_{idx}", fact),
        )


def _upsert_summary(case_id_mysql: int, summary_text: str) -> None:
    _mysql_execute("DELETE FROM case_summaries WHERE case_id=%s", (case_id_mysql,))
    _mysql_execute(
        """
        INSERT INTO case_summaries (case_id, summary_type, summary_text, model_used)
        VALUES (%s, %s, %s, %s)
        """,
        (case_id_mysql, "judgment", summary_text, "bart-large-cnn-or-fallback"),
    )


def _upsert_translation(case_id_mysql: int, language_code: str, translated_summary: str, model_used: str) -> None:
    _mysql_execute("DELETE FROM case_translations WHERE case_id=%s", (case_id_mysql,))
    _mysql_execute(
        """
        INSERT INTO case_translations (case_id, language_code, translated_summary, model_used)
        VALUES (%s, %s, %s, %s)
        """,
        (case_id_mysql, language_code, translated_summary, model_used),
    )


def _upsert_prediction(case_id_mysql: int, result: Dict[str, Any]) -> None:
    _mysql_execute("DELETE FROM case_predictions WHERE case_id=%s", (case_id_mysql,))
    _mysql_execute(
        """
        INSERT INTO case_predictions (
            case_id, predicted_outcome, win_probability, confidence_score, key_factors, model_version
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            case_id_mysql,
            result.get("prediction"),
            float(result.get("confidence", 0.0)),
            float(result.get("confidence", 0.0)),
            "text-classification",
            "lr-v1",
        ),
    )


def _replace_similar_cases(source_case_id: int, similar_case_numbers: List[str]) -> None:
    _mysql_execute("DELETE FROM similar_cases WHERE case_id=%s", (source_case_id,))
    for scn in similar_case_numbers:
        target_case_id = _get_case_id_mysql(scn)
        if target_case_id and target_case_id != source_case_id:
            _mysql_execute(
                """
                INSERT INTO similar_cases (case_id, similar_case_id, similarity_score)
                VALUES (%s, %s, %s)
                """,
                (source_case_id, target_case_id, 0.7),
            )


def _insert_ai_output(case_id: Any, case_number: str, stage: str, payload: Dict[str, Any]) -> None:
    db = get_db()
    db["ai_outputs"].insert_one(
        {
            "case_id": case_id,
            "case_number": case_number,
            "stage": stage,
            "output": payload,
            "created_at": _utcnow(),
        }
    )


def _process_stage(job: Dict[str, Any]) -> str:
    db = get_db()
    case_id = job["case_id"]
    case_number = job["case_number"]
    stage = job["stage"]

    case_doc = db["raw_judgments"].find_one({"_id": case_id})
    if not case_doc:
        raise RuntimeError("Case not found in raw_judgments")

    raw_text = case_doc.get("judgment_text", {}).get("raw_text", "")
    clean_text = case_doc.get("judgment_text", {}).get("clean_text", "")

    if stage == "uploaded":
        return "extracted"

    if stage == "extracted":
        normalized = _clean_text(raw_text)
        language_code = detect_language_code(normalized)
        paragraphs = split_paragraphs(normalized)
        title = _first_line_title(normalized)
        case_id_mysql = _upsert_case_mysql(case_number, title, normalized)

        db["raw_judgments"].update_one(
            {"_id": case_id},
            {
                "$set": {
                    "case_id_mysql": case_id_mysql,
                    "title": title,
                    "judgment_text.clean_text": normalized,
                    "judgment_text.paragraphs": paragraphs,
                    "judgment_text.language": language_code,
                    "judgment_text.token_count": len(normalized.split()),
                    "nlp_flags.text_cleaned": True,
                    "processing_status": "cleaned",
                    "last_updated_at": _utcnow(),
                }
            },
        )
        _insert_ai_output(case_id, case_number, "cleaned", {"token_count": len(normalized.split())})
        _log_system("pipeline", "cleaned", case_number)
        return "cleaned"

    if stage == "cleaned":
        clean_text = clean_text or _clean_text(raw_text)
        case_id_mysql = case_doc.get("case_id_mysql") or _get_case_id_mysql(case_number)
        facts = _extract_facts(clean_text)
        structured_summary = summarize_structured(clean_text)
        summary = "\n".join([f"- {p}" for p in structured_summary.get("key_points", [])])

        db["case_facts"].update_one(
            {"case_id": case_id},
            {"$set": {"case_id": case_id, "case_number": case_number, "facts": facts, "updated_at": _utcnow()}},
            upsert=True,
        )
        db["case_summaries"].update_one(
            {"case_id": case_id},
            {
                "$set": {
                    "case_id": case_id,
                    "case_number": case_number,
                    "summary": summary,
                    "short_summary": structured_summary.get("short_summary"),
                    "detailed_summary": structured_summary.get("detailed_summary"),
                    "key_points": structured_summary.get("key_points"),
                    "updated_at": _utcnow(),
                }
            },
            upsert=True,
        )
        if case_id_mysql:
            _mysql_execute("DELETE FROM case_facts WHERE case_id=%s", (case_id_mysql,))
            _insert_fact_rows(case_id_mysql, facts)
            _upsert_summary(case_id_mysql, structured_summary.get("detailed_summary", summary))

        db["raw_judgments"].update_one(
            {"_id": case_id},
            {
                "$set": {
                    "case_id_mysql": case_id_mysql,
                    "nlp_flags.entities_extracted": True,
                    "nlp_flags.summarized": True,
                    "processing_status": "summarized",
                    "last_updated_at": _utcnow(),
                }
            },
        )
        _insert_ai_output(case_id, case_number, "facts", {"facts": facts})
        _insert_ai_output(case_id, case_number, "summary", structured_summary)
        _log_system("pipeline", "summarized", case_number)
        return "summarized"

    if stage == "summarized":
        clean_text = clean_text or _clean_text(raw_text)
        case_id_mysql = case_doc.get("case_id_mysql") or _get_case_id_mysql(case_number)
        translation = _translate_text(clean_text)
        primary_lang = "en" if "en" in translation else next(iter(translation.keys()))
        primary_payload = translation.get(primary_lang, {})
        primary_translation = primary_payload.get("translated_text", clean_text)
        primary_model = primary_payload.get("model_used", "fallback-rule")

        db["case_translations"].update_one(
            {"case_id": case_id},
            {
                "$set": {
                    "case_id": case_id,
                    "case_number": case_number,
                    "translation": translation,
                    "updated_at": _utcnow(),
                }
            },
            upsert=True,
        )
        if case_id_mysql:
            _upsert_translation(case_id_mysql, primary_lang, primary_translation, primary_model)

        db["raw_judgments"].update_one(
            {"_id": case_id},
            {"$set": {"nlp_flags.translated": True, "processing_status": "translated", "last_updated_at": _utcnow()}},
        )
        _insert_ai_output(
            case_id,
            case_number,
            "translation",
            {
                "languages": list(translation.keys()),
                "model_used": {k: v.get("model_used") for k, v in translation.items()},
            },
        )
        _log_system("pipeline", "translated", case_number)
        return "translated"

    if stage == "translated":
        clean_text = clean_text or _clean_text(raw_text)
        chunks = _chunk_text(clean_text)
        db["case_chunks"].delete_many({"case_id": case_id})
        if chunks:
            db["case_chunks"].insert_many(
                [
                    {
                        "case_id": case_id,
                        "case_number": case_number,
                        "chunk_index": idx,
                        "text": chunk,
                        "created_at": _utcnow(),
                    }
                    for idx, chunk in enumerate(chunks)
                ]
            )
        db["raw_judgments"].update_one(
            {"_id": case_id},
            {
                "$set": {
                    "chunking.chunk_count": len(chunks),
                    "chunking.chunk_size": 180,
                    "chunking.overlap": 40,
                    "chunking.last_chunked_at": _utcnow(),
                    "nlp_flags.chunks_created": True,
                    "processing_status": "chunked",
                    "last_updated_at": _utcnow(),
                }
            },
        )
        _insert_ai_output(case_id, case_number, "chunks", {"chunk_count": len(chunks)})
        _log_system("pipeline", "chunked", case_number)
        return "chunked"

    if stage == "chunked":
        case_id_mysql = case_doc.get("case_id_mysql") or _get_case_id_mysql(case_number)
        chunks = list(db["case_chunks"].find({"case_id": case_id}).sort("chunk_index", 1))
        db["embeddings_metadata"].delete_many({"case_id": case_id})
        embedded_count = 0

        for chunk in chunks:
            text = chunk.get("text", "")
            vector = get_embedding(text)
            if vector is None:
                continue
            vector_store.add_case(case_number, text)
            db["embeddings_metadata"].insert_one(
                {
                    "case_id": case_id,
                    "case_number": case_number,
                    "chunk_index": chunk.get("chunk_index", 0),
                    "model": "all-MiniLM-L6-v2",
                    "dimension": int(len(vector)),
                    "created_at": _utcnow(),
                }
            )
            embedded_count += 1

        similar = vector_store.search(clean_text or raw_text, k=5)
        similar_filtered = [x for x in similar if x != case_number][:5]
        if case_id_mysql:
            _replace_similar_cases(case_id_mysql, similar_filtered)

        db["raw_judgments"].update_one(
            {"_id": case_id},
            {
                "$set": {
                    "embedding.embedding_model": "all-MiniLM-L6-v2",
                    "embedding.vector_dimension": 384,
                    "embedding.stored_in_vector_db": embedded_count > 0,
                    "embedding.embedded_at": _utcnow(),
                    "nlp_flags.embedded": True,
                    "processing_status": "embedded",
                    "last_updated_at": _utcnow(),
                }
            },
        )
        _insert_ai_output(
            case_id, case_number, "embeddings", {"embedded_chunks": embedded_count, "similar_cases": similar_filtered}
        )
        _log_system("pipeline", "embedded", case_number)
        return "embedded"

    if stage == "embedded":
        clean_text = clean_text or _clean_text(raw_text)
        case_id_mysql = case_doc.get("case_id_mysql") or _get_case_id_mysql(case_number)
        prediction = predict_case_with_history(clean_text)
        if case_id_mysql:
            _upsert_prediction(case_id_mysql, prediction)

        db["case_predictions"].update_one(
            {"case_id": case_id},
            {
                "$set": {
                    "case_id": case_id,
                    "case_number": case_number,
                    "prediction": prediction.get("prediction"),
                    "confidence": prediction.get("confidence"),
                    "updated_at": _utcnow(),
                }
            },
            upsert=True,
        )
        db["raw_judgments"].update_one(
            {"_id": case_id},
            {
                "$set": {
                    "prediction.predicted_outcome": prediction.get("prediction"),
                    "prediction.confidence_score": prediction.get("confidence"),
                    "prediction.predicted_at": _utcnow(),
                    "nlp_flags.prediction_done": True,
                    "processing_status": "predicted",
                    "last_updated_at": _utcnow(),
                }
            },
        )
        _insert_ai_output(case_id, case_number, "prediction", prediction)
        _log_system("pipeline", "predicted", case_number)
        return "predicted"

    if stage == "predicted":
        db["raw_judgments"].update_one(
            {"_id": case_id},
            {"$set": {"processing_status": "completed", "last_updated_at": _utcnow()}},
        )
        _log_system("pipeline", "completed", case_number)
        return "completed"

    return "completed"


def enqueue_case(case_id: Any, case_number: str, stage: str = "extracted") -> None:
    db = get_db()
    now = _utcnow()
    db["processing_queue"].update_one(
        {"case_id": case_id},
        {
            "$set": {
                "case_id": case_id,
                "case_number": case_number,
                "stage": stage,
                "status": "pending",
                "error": None,
                "updated_at": now,
            },
            "$setOnInsert": {"attempts": 0, "created_at": now},
        },
        upsert=True,
    )


def _claim_next_job() -> Optional[Dict[str, Any]]:
    db = get_db()
    now = _utcnow()
    return db["processing_queue"].find_one_and_update(
        {"status": {"$in": ["pending", "retry"]}},
        {"$set": {"status": "processing", "worker_id": WORKER_ID, "started_at": now, "updated_at": now}},
        sort=[("updated_at", 1)],
        return_document=ReturnDocument.AFTER,
    )


def _finish_job(job_id: Any, next_stage: str) -> None:
    db = get_db()
    now = _utcnow()
    if next_stage == "completed":
        db["processing_queue"].update_one(
            {"_id": job_id},
            {
                "$set": {"stage": "completed", "status": "completed", "finished_at": now, "updated_at": now},
                "$unset": {"worker_id": "", "started_at": ""},
            },
        )
    else:
        db["processing_queue"].update_one(
            {"_id": job_id},
            {
                "$set": {"stage": next_stage, "status": "pending", "updated_at": now},
                "$unset": {"worker_id": "", "started_at": ""},
            },
        )


def _fail_job(job: Dict[str, Any], error: Exception) -> None:
    db = get_db()
    attempts = int(job.get("attempts", 0)) + 1
    now = _utcnow()
    status = "failed" if attempts >= MAX_RETRIES else "retry"
    db["processing_queue"].update_one(
        {"_id": job["_id"]},
        {
            "$set": {"status": status, "error": str(error), "updated_at": now},
            "$inc": {"attempts": 1},
            "$unset": {"worker_id": "", "started_at": ""},
        },
    )
    db["raw_judgments"].update_one(
        {"_id": job["case_id"]},
        {"$set": {"processing_status": "failed", "last_updated_at": now}, "$push": {"error_logs": f"{now} {error}"}},
    )
    _log_system("pipeline", "error", str(error))


def process_next_job() -> bool:
    job = _claim_next_job()
    if not job:
        return False
    try:
        next_stage = _process_stage(job)
        _finish_job(job["_id"], next_stage)
    except Exception as exc:
        _fail_job(job, exc)
    return True


class PipelineWorker:
    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name="pipeline-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            processed = process_next_job()
            if not processed:
                time.sleep(WORKER_POLL_SECONDS)


pipeline_worker = PipelineWorker()
