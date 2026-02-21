"""
Fixed AI routes:
- /summarize → also returns basic_summary (plain-language, max 6 sentences)
- /translate  → translates basic_summary + key_points (NOT raw document text)
- /case/{case_id} → returns full stored case for similar-case viewer
"""
from fastapi import APIRouter
from backend.database.mongo import get_db
from backend.database.mysql import get_mysql_connection
from backend.ai.predictor import predict_case_with_history
from backend.ai.summarizer import summarize_structured, make_basic_summary
from backend.ai.translator import translate_text, LANGUAGE_NAMES, translate_for_chatbot
from backend.routes.similarity_routes import find_similar_cases
from bson import ObjectId

router = APIRouter(prefix="/ai", tags=["AI"])


# ─── /summarize/{case_number} ────────────────────────────────────────────────
@router.get("/summarize/{case_number:path}")
def summarize_case(case_number: str):
    db = get_db()
    case = db["raw_judgments"].find_one({"case_number": case_number})
    if not case:
        return {"error": "Case not found"}

    text = case.get("judgment_text", {}).get("clean_text") or case.get("judgment_text", {}).get("raw_text", "")
    structured = summarize_structured(text)
    basic      = make_basic_summary(text)

    # Merge basic into structured result
    structured["basic_summary"] = basic

    case_id     = str(case.get("_id"))
    case_id_mysql = case.get("case_id_mysql")
    # key_points are now {label, explanation} dicts
    kp = structured.get("key_points", [])
    if kp and isinstance(kp[0], dict):
        summary_str = "\n".join([f"- {p['label']}: {p['explanation']}" for p in kp])
    else:
        summary_str = "\n".join([f"- {p}" for p in kp])

    db["case_summaries"].update_one(
        {"case_id": case_id},
        {"$set": {
            "case_id":       case_id,
            "case_number":   case_number,
            "summary":       summary_str,
            "short_summary": structured.get("short_summary"),
            "basic_summary": basic,
            "detailed_summary": structured.get("detailed_summary"),
            "key_points":    structured.get("key_points"),
        }},
        upsert=True,
    )

    if case_id_mysql:
        conn = cursor = None
        try:
            conn   = get_mysql_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM case_summaries WHERE case_id=%s", (case_id_mysql,))
            cursor.execute(
                "INSERT INTO case_summaries (case_id, summary_type, summary_text, model_used) VALUES (%s,%s,%s,%s)",
                (case_id_mysql, "judgment", summary_str, "rule-based"),
            )
            conn.commit()
        except Exception:
            pass
        finally:
            if cursor: cursor.close()
            if conn:   conn.close()

    return {"case_number": case_number, "summary": structured}


# ─── /translate/{case_number} ────────────────────────────────────────────────
@router.get("/translate/{case_number:path}")
def translate_case(case_number: str, language: str = "hi", mode: str = "summary"):
    """
    Translate a case to a regional language.
    mode=summary (default): translate basic_summary + key_points  ← spec default
    mode=raw              : translate the full clean document text (user-initiated only)

    Cache-first: if a translation for (case_number, language, mode) already
    exists in MongoDB, return it immediately without re-translating.

    Legal tokens (section numbers, act names, dates) and party/judge names
    are protected from translation via placeholder substitution.

    Output format per spec:
    { language, translated_text, source_language, language_name, mode, model_used, error }
    """
    db = get_db()
    case = db["raw_judgments"].find_one({"case_number": case_number})
    if not case:
        return {"error": "Case not found"}

    # ── Cache check ─────────────────────────────────────────────────────────
    cached = db["case_translations"].find_one(
        {"case_number": case_number, "language": language, "mode": mode}
    )
    if cached and cached.get("translated_text"):
        return {
            "case_number":      case_number,
            "language":         language,
            "language_name":    LANGUAGE_NAMES.get(language, language.upper()),
            "mode":             mode,
            "translated_text":  cached["translated_text"],
            "source_language":  "en",
            "model_used":       cached.get("model_used", "cached"),
            "error":            None,
            "cached":           True,
        }

    # ── Extract proper nouns to protect from translation ────────────────────
    meta = case.get("case_metadata") or {}
    extra_protect = []
    for field in ("petitioner", "respondent", "judge_names", "court_name"):
        val = meta.get(field)
        if val and isinstance(val, str) and val.lower() not in ("unknown", ""):
            for part in val.split(","):
                part = part.strip()
                if len(part) > 2:
                    extra_protect.append(part)

    # ── Build translation source text ────────────────────────────────────────
    if mode == "raw":
        # Full document — only translate on explicit user request
        text = (
            case.get("judgment_text", {}).get("clean_text")
            or case.get("judgment_text", {}).get("raw_text", "")
        )
        if not text:
            return {"error": "No document text found. Please upload and process the document first."}
        translate_src = text.strip()
        src_label = "document text"

    else:
        # Summary mode (default) — translate ONLY user-facing summary fields
        stored_summary = db["case_summaries"].find_one({"case_number": case_number})
        if stored_summary:
            basic   = stored_summary.get("basic_summary") or stored_summary.get("short_summary") or ""
            kpoints = stored_summary.get("key_points") or []
        else:
            # Generate on the fly if pipeline hasn't run yet
            text       = (case.get("judgment_text", {}).get("clean_text")
                          or case.get("judgment_text", {}).get("raw_text", ""))
            structured = summarize_structured(text)
            basic      = make_basic_summary(text)
            kpoints    = structured.get("key_points", [])

        key_str       = "\n".join([f"{i+1}. {p}" for i, p in enumerate(kpoints)])
        translate_src = f"{basic}\n\nKey Points:\n{key_str}".strip()
        src_label     = "summary"

    if not translate_src:
        return {"error": f"No {src_label} available. Run Summarize first."}

    # ── Perform translation (with legal token + proper noun protection) ──────
    result   = translate_text(
        translate_src,
        target_languages=[language],
        source_language="en",
        extra_protect=extra_protect or None,
    )
    selected = result.get(
        language,
        {
            "language":        language,
            "translated_text": translate_src,
            "source_language": "en",
            "model_used":      "english-fallback",
            "error":           "Language not supported",
        },
    )

    output      = selected.get("translated_text", translate_src)
    model_used  = selected.get("model_used", "unknown")
    err         = selected.get("error")

    # ── Persist to cache (store even on error so we don't retry repeatedly) ─
    db["case_translations"].update_one(
        {"case_number": case_number, "language": language, "mode": mode},
        {"$set": {
            "case_number":     case_number,
            "language":        language,
            "mode":            mode,
            "translated_text": output,
            "source_language": "en",
            "model_used":      model_used,
            "error":           err,
        }},
        upsert=True,
    )

    return {
        "case_number":     case_number,
        "language":        language,
        "language_name":   LANGUAGE_NAMES.get(language, language.upper()),
        "mode":            mode,
        "translated_text": output,
        "source_language": "en",
        "model_used":      model_used,
        "error":           err,   # None on success
        "cached":          False,
    }


# ─── /case/{case_id} ─────────────────────────────────────────────────────────
@router.get("/case/{case_id}")
def get_case_by_id(case_id: str):
    """Return a full stored case record by MongoDB _id. Used for similar-case click."""
    db = get_db()
    try:
        oid = ObjectId(case_id)
    except Exception:
        return {"error": "Invalid case ID format"}

    doc = db["raw_judgments"].find_one({"_id": oid})
    if not doc:
        return {"error": "Case not found"}

    # Fetch stored summary if exists
    stored_summary = db["case_summaries"].find_one({"case_id": str(oid)})

    return {
        "case_id":      str(doc["_id"]),
        "case_number":  doc.get("case_number"),
        "title":        doc.get("title"),
        "case_metadata": doc.get("case_metadata", {}),
        "processing_status": doc.get("processing_status"),
        "language_code": doc.get("judgment_text", {}).get("language"),
        "paragraph_count": len(doc.get("judgment_text", {}).get("paragraphs") or []),
        "created_at":   str(doc.get("created_at", "")),
        "summary": {
            "short_summary":   (stored_summary or {}).get("short_summary"),
            "basic_summary":   (stored_summary or {}).get("basic_summary"),
            "key_points":      (stored_summary or {}).get("key_points", []),
        } if stored_summary else None,
    }


# ─── /analyze/{case_number} ──────────────────────────────────────────────────
@router.get("/analyze/{case_number:path}")
def full_case_analysis(case_number: str, language: str = "en"):
    db = get_db()
    case = db["raw_judgments"].find_one({"case_number": case_number})
    if not case:
        return {"error": "Case not found"}

    text      = case.get("judgment_text", {}).get("clean_text") or case.get("judgment_text", {}).get("raw_text", "")
    summaries = summarize_structured(text)
    basic     = make_basic_summary(text)
    summaries["basic_summary"] = basic

    translate_src = basic + "\n\nKey Points:\n" + "\n".join(summaries.get("key_points", []))
    translation_map = translate_text(translate_src, [language])
    tsel  = translation_map.get(language, {"translated_text": translate_src, "model_used": "fallback"})
    similar = find_similar_cases(case_number, top_k=5)
    similar_cases = similar.get("similar_cases", []) if isinstance(similar, dict) else []
    pred  = predict_case_with_history(text)

    return {
        "translation": {
            "language":   language,
            "text":       tsel.get("translated_text", translate_src),
            "model_used": tsel.get("model_used", "fallback"),
        },
        "summaries":   summaries,
        "similar_cases": similar_cases,
        "prediction": {
            "outcome":     pred.get("prediction"),
            "probability": pred.get("confidence"),
            "confidence":  pred.get("confidence"),
            "factors":     pred.get("important_factors", []),
        },
    }
