"""
backend/routes/intelligence_routes.py

Database Intelligence API — exposes per-feature table routing
and cross-table analytics for the Legal AI platform.

All data sourced exclusively from MySQL.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.services.db_intelligence import (
    # BNS Mapper
    bns_get_mapping, bns_get_section, bns_search_keyword, bns_save_feedback,
    # Predict Outcome
    predict_get_case_facts, predict_get_stored_prediction,
    predict_get_judge_analytics, predict_get_similar_cases,
    # ADR
    adr_get_assessment, adr_get_lok_adalat_eligible,
    adr_get_lok_adalat_awards, adr_avg_settlement_by_type,
    # Summaries
    summary_get_stored,
    # Similar
    similar_get_for_case, similar_get_citations,
    # eCourts
    ecourts_get_status, ecourts_recent_syncs,
    # Reports
    reports_get_section_report, reports_get_case_acts,
    # Translation
    translation_get, translation_get_section,
    # Chat
    chat_get_history, chat_get_case_context,
    # Monitoring
    logs_get_recent_errors,
    # Cross-feature
    case_full_intelligence, platform_stats,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/intelligence", tags=["db-intelligence"])


# ── Pydantic Models ───────────────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    old_act:     str
    old_section: str
    new_act:     str
    new_section: str
    feedback:    str
    user:        Optional[str] = "user"


# ── BNS Mapper ────────────────────────────────────────────────────────────────

@router.get("/bns/mapping")
def get_bns_mapping(
    act: str = Query(..., description="IPC / CrPC / IEA / BNS / BNSS / BSA"),
    section: str = Query(..., description="Section number e.g. 302"),
):
    """BNS Mapper: section_mapping + sections."""
    row = bns_get_mapping(act, section)
    if not row:
        row = bns_get_section(act, section)   # fallback: raw section content
    if not row:
        raise HTTPException(404, f"No mapping or section found for {act} {section}")
    return row


@router.get("/bns/section")
def get_bns_section(
    act: str = Query(...),
    section: str = Query(...),
):
    """Full section content from sections table."""
    row = bns_get_section(act, section)
    if not row:
        raise HTTPException(404, f"{act} {section} not found in sections table.")
    return row


@router.get("/bns/search")
def search_bns(q: str = Query(..., min_length=2)):
    """Keyword search across section_mapping titles."""
    return {"results": bns_search_keyword(q), "query": q}


@router.post("/bns/feedback")
def submit_feedback(req: FeedbackRequest):
    """Save mapping correction to section_mapping_feedback."""
    ok = bns_save_feedback(req.old_act, req.old_section,
                           req.new_act, req.new_section,
                           req.feedback, req.user)
    if not ok:
        raise HTTPException(500, "Failed to save feedback.")
    return {"saved": True}


# ── Predict Outcome ───────────────────────────────────────────────────────────

@router.get("/predict/facts/{case_number:path}")
def get_case_facts(case_number: str):
    """Case facts for AI prediction — case_facts + cases join."""
    row = predict_get_case_facts(case_number)
    if not row:
        raise HTTPException(404, f"No facts found for {case_number}")
    return row


@router.get("/predict/result/{case_number:path}")
def get_prediction(case_number: str):
    """Stored AI prediction from case_predictions."""
    row = predict_get_stored_prediction(case_number)
    if not row:
        raise HTTPException(404, "No prediction stored. Run /ai/predict first.")
    return row


@router.get("/predict/judge")
def get_judge_stats(name: str = Query(..., min_length=3)):
    """Judge analytics for prediction calibration."""
    row = predict_get_judge_analytics(name)
    if not row:
        raise HTTPException(404, f"No analytics found for judge '{name}'")
    return row


# ── ADR Checker ───────────────────────────────────────────────────────────────

@router.get("/adr/{case_number:path}")
def get_adr_assessment(case_number: str):
    """ADR suitability from adr_suitability table."""
    row = adr_get_assessment(case_number)
    if not row:
        raise HTTPException(404, "No ADR assessment stored for this case.")
    return row


@router.get("/adr-eligible")
def get_lok_adalat_eligible(limit: int = Query(20, le=100)):
    """Top Lok Adalat eligible cases from adr_suitability."""
    return {"cases": adr_get_lok_adalat_eligible(limit)}


@router.get("/lok-adalat-awards")
def get_awards(
    case_type: Optional[str] = Query(None),
    limit: int = Query(10, le=50),
):
    """Lok Adalat award records for settlement benchmarking."""
    awards = adr_get_lok_adalat_awards(case_type, limit)
    bench = adr_avg_settlement_by_type(case_type) if case_type else None
    return {"awards": awards, "benchmark": bench}


# ── Case Summaries ────────────────────────────────────────────────────────────

@router.get("/summary/{case_number:path}")
def get_summary(case_number: str):
    """AI case summary from case_summaries."""
    row = summary_get_stored(case_number)
    if not row:
        raise HTTPException(404, "No summary found. Process document first.")
    return row


# ── Similar Cases ─────────────────────────────────────────────────────────────

@router.get("/similar/{case_number:path}")
def get_similar(case_number: str, limit: int = Query(5, le=20)):
    """Similar cases from similar_cases table."""
    results = similar_get_for_case(case_number, limit)
    citations = similar_get_citations(case_number)
    return {"similar_cases": results, "citations": citations}


# ── eCourts ───────────────────────────────────────────────────────────────────

@router.get("/ecourts/{cnr_or_case:path}")
def get_ecourts_cache(cnr_or_case: str):
    """eCourts cached data — ecourts_case_status lookup."""
    row = ecourts_get_status(cnr_or_case)
    if not row:
        raise HTTPException(404, "Not in cache. Sync from eCourts first.")
    return row


@router.get("/ecourts-sync-log")
def get_sync_log(limit: int = Query(20, le=100)):
    """Recent eCourts sync events from ecourts_sync_log."""
    return {"events": ecourts_recent_syncs(limit)}


# ── Legal Reports ─────────────────────────────────────────────────────────────

@router.get("/report/{case_number:path}")
def get_report(case_number: str):
    """BNS citation audit report + applied acts for a case."""
    report = reports_get_section_report(case_number)
    acts   = reports_get_case_acts(case_number)
    if not report and not acts:
        raise HTTPException(404, "No report found for this case.")
    return {"section_report": report, "case_acts": acts}


# ── Translation ───────────────────────────────────────────────────────────────

@router.get("/translation/{case_number:path}")
def get_translation(
    case_number: str,
    lang: str = Query("hi", description="Language code: hi, mr, ta, te, kn, gu"),
):
    """Stored translation from case_translations."""
    row = translation_get(case_number, lang)
    if not row:
        raise HTTPException(404, f"No {lang} translation found for {case_number}.")
    return row


@router.get("/section-translation")
def get_section_translation(
    act: str = Query(...),
    section: str = Query(...),
    lang: str = Query("hi"),
):
    """Translated section text from sections + case_translations join."""
    row = translation_get_section(act, section, lang)
    if not row:
        raise HTTPException(404, "No translation found for this section.")
    return row


# ── Chat Context ──────────────────────────────────────────────────────────────

@router.get("/chat-context/{case_number:path}")
def get_chat_context(case_number: str):
    """Case context for chat assistant — cases + ecourts + adr join."""
    row = chat_get_case_context(case_number)
    if not row:
        raise HTTPException(404, "Case not found in database.")
    return row


@router.get("/chat-history/{session_id}")
def get_chat_history(session_id: str, limit: int = Query(20, le=100)):
    """Chat history for a session from chat_history."""
    return {"session_id": session_id, "messages": chat_get_history(session_id, limit)}


# ── System Monitoring ─────────────────────────────────────────────────────────

@router.get("/system-errors")
def get_system_errors(limit: int = Query(50, le=200)):
    """Recent errors/warnings from system_logs."""
    return {"logs": logs_get_recent_errors(limit)}


# ── Cross-feature: Full Case Intelligence ─────────────────────────────────────

@router.get("/case/{case_number:path}")
def get_case_intelligence(case_number: str):
    """
    Full 360° case intelligence — aggregates:
    cases · ecourts_case_status · adr_suitability · case_section_reports
    · case_predictions · similar_cases · case_summaries
    """
    result = case_full_intelligence(case_number)
    if not result.get("case"):
        raise HTTPException(404, f"Case '{case_number}' not found in MySQL.")
    return result


# ── Platform Stats (MySQL-only dashboard) ─────────────────────────────────────

@router.get("/stats")
def get_platform_stats():
    """
    Platform-wide statistics from MySQL only.
    Replaces the MongoDB-based dashboard counts.
    """
    return platform_stats()
