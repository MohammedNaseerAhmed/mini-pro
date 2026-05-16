"""
backend/services/db_intelligence.py

Database Intelligence Layer for the Legal AI Platform.

ROUTING RULES:
  BNS Mapper          → section_mapping + sections
  Predict Outcome     → case_facts + case_predictions + judge_analytics + similar_cases
  ADR Checker         → adr_suitability + lok_adalat_awards + case_facts
  Case Summarization  → case_facts + case_summaries
  Similar Case Search → similar_cases + case_section_citations + case_facts
  eCourts Feature     → ecourts_case_status + ecourts_sync_log
  Translation Feature → case_translations + sections
  Legal Reports       → case_section_reports + sections + case_acts
  Chat Assistant      → chat_history + cases + sections

RULES:
  - MySQL is the ONLY source of truth
  - No JSON files, no hardcoded data, no hallucinations
  - Use indexed fields + selective column fetching
  - sections_backup is NEVER used in production
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.database.mysql import get_mysql_connection

logger = logging.getLogger(__name__)


# ── Generic safe query executor ───────────────────────────────────────────────

def _q(sql: str, params: tuple = (), many: bool = True) -> Any:
    """Execute a SELECT and return list of dicts (many=True) or single dict."""
    conn = None
    try:
        conn = get_mysql_connection()
        cur  = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        return cur.fetchall() if many else cur.fetchone()
    except Exception as exc:
        logger.error("[DB] Query failed: %s | params=%s | err=%s", sql[:120], params, exc)
        return [] if many else None
    finally:
        if conn:
            try: conn.close()
            except Exception: pass


def _w(sql: str, params: tuple = ()) -> bool:
    """Execute an INSERT/UPDATE/DELETE. Returns True on success."""
    conn = None
    try:
        conn = get_mysql_connection()
        cur  = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        return True
    except Exception as exc:
        logger.error("[DB] Write failed: %s | err=%s", sql[:120], exc)
        return False
    finally:
        if conn:
            try: conn.close()
            except Exception: pass


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE: BNS Mapper  →  section_mapping + sections
# ══════════════════════════════════════════════════════════════════════════════

def bns_get_mapping(old_act: str, old_section: str) -> Optional[Dict]:
    """Exact old→new lookup from section_mapping joined to sections."""
    return _q(
        """
        SELECT sm.old_act, sm.old_section, sm.old_title,
               sm.new_act, sm.new_section, sm.new_title,
               sm.change_type, sm.change_notes,
               s.content, s.full_description, s.punishment
        FROM section_mapping sm
        LEFT JOIN sections s ON sm.new_section_id = s.id
        WHERE sm.old_act = %s AND sm.old_section = %s
        LIMIT 1
        """,
        (old_act.upper(), old_section.strip()),
        many=False,
    )


def bns_get_section(act: str, section: str) -> Optional[Dict]:
    """Fetch full section content from sections table."""
    return _q(
        """
        SELECT id, act_name, section_number, title,
               content, full_description, punishment
        FROM sections
        WHERE act_name = %s AND section_number = %s
        LIMIT 1
        """,
        (act.upper(), section.strip()),
        many=False,
    )


def bns_search_keyword(keyword: str, limit: int = 30) -> List[Dict]:
    """Search section_mapping by keyword in titles."""
    like = f"%{keyword.strip()}%"
    return _q(
        """
        SELECT sm.old_act, sm.old_section, sm.old_title,
               sm.new_act, sm.new_section, sm.new_title,
               sm.change_type, s.punishment
        FROM section_mapping sm
        LEFT JOIN sections s ON sm.new_section_id = s.id
        WHERE sm.old_title LIKE %s OR sm.new_title LIKE %s
        LIMIT %s
        """,
        (like, like, limit),
    )


def bns_save_feedback(old_act: str, old_sec: str, new_act: str,
                      new_sec: str, feedback: str, user: str = "user") -> bool:
    """Persist user mapping correction to section_mapping_feedback."""
    return _w(
        """
        INSERT INTO section_mapping_feedback
            (old_act, old_section, suggested_new_act, suggested_new_section,
             feedback_text, submitted_by, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """,
        (old_act, old_sec, new_act, new_sec, feedback, user),
    )


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE: Predict Outcome  →  case_facts + case_predictions + judge_analytics + similar_cases
# ══════════════════════════════════════════════════════════════════════════════

def predict_get_case_facts(case_number: str) -> Optional[Dict]:
    """Load case narrative facts for AI prediction input."""
    return _q(
        """
        SELECT cf.case_id, cf.facts_text, cf.fir_details,
               cf.incident_date, cf.incident_location,
               c.case_number, c.case_type, c.court_name, c.filing_date
        FROM case_facts cf
        JOIN cases c ON cf.case_id = c.case_id
        WHERE c.case_number = %s
        LIMIT 1
        """,
        (case_number,),
        many=False,
    )


def predict_get_stored_prediction(case_number: str) -> Optional[Dict]:
    """Fetch AI prediction from case_predictions."""
    return _q(
        """
        SELECT cp.case_id, cp.predicted_outcome, cp.conviction_probability,
               cp.acquittal_probability, cp.risk_score, cp.ai_reasoning,
               cp.prediction_model, cp.created_at
        FROM case_predictions cp
        JOIN cases c ON cp.case_id = c.case_id
        WHERE c.case_number = %s
        ORDER BY cp.created_at DESC
        LIMIT 1
        """,
        (case_number,),
        many=False,
    )


def predict_get_judge_analytics(judge_name: str) -> Optional[Dict]:
    """Fetch judge statistics for prediction calibration."""
    return _q(
        """
        SELECT judge_name, total_cases, conviction_rate, acquittal_rate,
               avg_disposal_days, most_common_case_type, bail_grant_rate
        FROM judge_analytics
        WHERE judge_name LIKE %s
        LIMIT 1
        """,
        (f"%{judge_name}%",),
        many=False,
    )


def predict_get_similar_cases(case_id: int, limit: int = 5) -> List[Dict]:
    """Get top similar cases for a given case_id from similar_cases."""
    return _q(
        """
        SELECT sc.similarity_score,
               c.case_number, c.case_type, c.court_name,
               cp.predicted_outcome, cp.conviction_probability
        FROM similar_cases sc
        JOIN cases c ON sc.similar_case_id = c.case_id
        LEFT JOIN case_predictions cp ON cp.case_id = c.case_id
        WHERE sc.case_id = %s
        ORDER BY sc.similarity_score DESC
        LIMIT %s
        """,
        (case_id, limit),
    )


def predict_save_prediction(case_id: int, outcome: str, conviction_pct: float,
                             acquittal_pct: float, risk: float,
                             reasoning: str, model: str = "groq") -> bool:
    """Persist AI prediction result to case_predictions."""
    return _w(
        """
        INSERT INTO case_predictions
            (case_id, predicted_outcome, conviction_probability,
             acquittal_probability, risk_score, ai_reasoning,
             prediction_model, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        ON DUPLICATE KEY UPDATE
            predicted_outcome      = VALUES(predicted_outcome),
            conviction_probability = VALUES(conviction_probability),
            acquittal_probability  = VALUES(acquittal_probability),
            risk_score             = VALUES(risk_score),
            ai_reasoning           = VALUES(ai_reasoning),
            prediction_model       = VALUES(prediction_model),
            created_at             = NOW()
        """,
        (case_id, outcome, conviction_pct, acquittal_pct, risk, reasoning, model),
    )


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE: ADR Checker  →  adr_suitability + lok_adalat_awards + case_facts
# ══════════════════════════════════════════════════════════════════════════════

def adr_get_assessment(case_number: str) -> Optional[Dict]:
    """Fetch stored ADR suitability assessment."""
    return _q(
        """
        SELECT case_number, case_type, lok_adalat_score, mediation_score,
               arbitration_score, negotiation_score, recommended_adr,
               is_lok_adalat_eligible, confidence_level, factors,
               predicted_settlement_amount, predicted_settlement_pct,
               predicted_days_to_settle, assessed_at
        FROM adr_suitability
        WHERE case_number = %s
        LIMIT 1
        """,
        (case_number,),
        many=False,
    )


def adr_get_lok_adalat_eligible(limit: int = 20) -> List[Dict]:
    """Get top Lok Adalat eligible cases sorted by score."""
    return _q(
        """
        SELECT case_number, case_type, lok_adalat_score,
               predicted_settlement_amount, assessed_at
        FROM adr_suitability
        WHERE is_lok_adalat_eligible = TRUE
        ORDER BY lok_adalat_score DESC
        LIMIT %s
        """,
        (limit,),
    )


def adr_get_lok_adalat_awards(case_type: str = None, limit: int = 10) -> List[Dict]:
    """Fetch Lok Adalat award records for settlement benchmarking."""
    if case_type:
        return _q(
            """
            SELECT case_type, award_amount, settlement_date,
                   authority, case_reference
            FROM lok_adalat_awards
            WHERE case_type = %s
            ORDER BY settlement_date DESC
            LIMIT %s
            """,
            (case_type, limit),
        )
    return _q(
        """
        SELECT case_type, award_amount, settlement_date,
               authority, case_reference
        FROM lok_adalat_awards
        ORDER BY settlement_date DESC
        LIMIT %s
        """,
        (limit,),
    )


def adr_avg_settlement_by_type(case_type: str) -> Optional[Dict]:
    """Aggregate avg settlement amount for a case type from lok_adalat_awards."""
    return _q(
        """
        SELECT case_type,
               COUNT(*) AS total_awards,
               AVG(award_amount) AS avg_amount,
               MIN(award_amount) AS min_amount,
               MAX(award_amount) AS max_amount
        FROM lok_adalat_awards
        WHERE case_type = %s
        GROUP BY case_type
        LIMIT 1
        """,
        (case_type,),
        many=False,
    )


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE: Case Summarization  →  case_facts + case_summaries
# ══════════════════════════════════════════════════════════════════════════════

def summary_get_stored(case_number: str) -> Optional[Dict]:
    """Fetch stored AI summary from case_summaries."""
    return _q(
        """
        SELECT cs.summary_text, cs.summary_type, cs.language,
               cs.word_count, cs.created_at,
               c.case_number, c.case_type, c.court_name
        FROM case_summaries cs
        JOIN cases c ON cs.case_id = c.case_id
        WHERE c.case_number = %s
        ORDER BY cs.created_at DESC
        LIMIT 1
        """,
        (case_number,),
        many=False,
    )


def summary_save(case_id: int, summary_text: str,
                 summary_type: str = "ai", language: str = "en") -> bool:
    """Persist generated summary to case_summaries."""
    word_count = len(summary_text.split())
    return _w(
        """
        INSERT INTO case_summaries
            (case_id, summary_text, summary_type, language, word_count, created_at)
        VALUES (%s, %s, %s, %s, %s, NOW())
        ON DUPLICATE KEY UPDATE
            summary_text = VALUES(summary_text),
            word_count   = VALUES(word_count),
            created_at   = NOW()
        """,
        (case_id, summary_text, summary_type, language, word_count),
    )


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE: Similar Case Search  →  similar_cases + case_section_citations + case_facts
# ══════════════════════════════════════════════════════════════════════════════

def similar_get_for_case(case_number: str, limit: int = 5) -> List[Dict]:
    """Retrieve top similar cases from similar_cases table."""
    return _q(
        """
        SELECT sc.similarity_score,
               c_src.case_number AS source_case,
               c_sim.case_number AS similar_case,
               c_sim.case_type, c_sim.court_name
        FROM similar_cases sc
        JOIN cases c_src ON sc.case_id      = c_src.case_id
        JOIN cases c_sim ON sc.similar_case_id = c_sim.case_id
        WHERE c_src.case_number = %s
        ORDER BY sc.similarity_score DESC
        LIMIT %s
        """,
        (case_number, limit),
    )


def similar_get_citations(case_number: str) -> List[Dict]:
    """Fetch section citations for a case (for citation graph / precedent)."""
    return _q(
        """
        SELECT csc.act_name, csc.section_number, csc.citation_context,
               csc.citation_type, csc.cited_in_judgment
        FROM case_section_citations csc
        JOIN cases c ON csc.case_id = c.case_id
        WHERE c.case_number = %s
        ORDER BY csc.act_name, csc.section_number
        """,
        (case_number,),
    )


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE: eCourts  →  ecourts_case_status + ecourts_sync_log
# ══════════════════════════════════════════════════════════════════════════════

def ecourts_get_status(cnr_or_case: str) -> Optional[Dict]:
    """Fetch cached eCourts status by CNR or case number."""
    key = cnr_or_case.strip().upper()
    return _q(
        """
        SELECT case_number, cnr_number, court_complex, judge_assigned,
               case_stage, next_hearing_date, petitioner_name, respondent_name,
               source, last_synced_at
        FROM ecourts_case_status
        WHERE cnr_number = %s OR case_number = %s
        ORDER BY last_synced_at DESC
        LIMIT 1
        """,
        (key, key),
        many=False,
    )


def ecourts_log_sync(cnr: str, status: str, message: str = "") -> bool:
    """Write a sync event to ecourts_sync_log."""
    return _w(
        """
        INSERT INTO ecourts_sync_log
            (cnr_number, sync_status, message, synced_at)
        VALUES (%s, %s, %s, NOW())
        """,
        (cnr, status, message[:500]),
    )


def ecourts_upsert_status(
    case_number: str,
    cnr: str,
    next_hearing: Optional[str] = None,
    case_stage: Optional[str] = None,
    petitioner: str = "",
    respondent: str = "",
    court_complex: str = "",
    judge: str = "",
    source: str = "pasted",
) -> bool:
    """
    INSERT … ON DUPLICATE KEY UPDATE for ecourts_case_status.
    Used by the paste-and-analyse workflow and any live-scrape persistence.
    Centralises the upsert so routes don't hold raw SQL.
    """
    return _w(
        """
        INSERT INTO ecourts_case_status
            (case_number, cnr_number, next_hearing_date, case_stage,
             petitioner_name, respondent_name, court_complex, judge_assigned,
             source, last_synced_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON DUPLICATE KEY UPDATE
            cnr_number        = VALUES(cnr_number),
            next_hearing_date = VALUES(next_hearing_date),
            case_stage        = VALUES(case_stage),
            petitioner_name   = VALUES(petitioner_name),
            respondent_name   = VALUES(respondent_name),
            court_complex     = VALUES(court_complex),
            judge_assigned    = VALUES(judge_assigned),
            source            = VALUES(source),
            last_synced_at    = NOW()
        """,
        (case_number, cnr, next_hearing, case_stage,
         petitioner[:200], respondent[:200], court_complex[:200], judge[:200],
         source),
    )


def ecourts_recent_syncs(limit: int = 20) -> List[Dict]:
    """Get recent sync events for monitoring."""
    return _q(
        """
        SELECT cnr_number, sync_status, message, synced_at
        FROM ecourts_sync_log
        ORDER BY synced_at DESC
        LIMIT %s
        """,
        (limit,),
    )


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE: Legal Reports  →  case_section_reports + sections + case_acts
# ══════════════════════════════════════════════════════════════════════════════

def reports_get_section_report(case_number: str) -> Optional[Dict]:
    """Fetch BNS citation audit report for a case."""
    return _q(
        """
        SELECT case_number, total_citations, unique_sections,
               deprecated_count, unmapped_count, document_era,
               has_deprecated_citations, citation_quality_score, created_at
        FROM case_section_reports
        WHERE case_number = %s
        LIMIT 1
        """,
        (case_number,),
        many=False,
    )


def reports_get_case_acts(case_number: str) -> List[Dict]:
    """Fetch applied legal acts/sections for a case from case_acts."""
    return _q(
        """
        SELECT ca.act_name, ca.section_number, ca.section_title,
               ca.applicability_note,
               s.content, s.punishment
        FROM case_acts ca
        JOIN cases c ON ca.case_id = c.case_id
        LEFT JOIN sections s
               ON s.act_name = ca.act_name AND s.section_number = ca.section_number
        WHERE c.case_number = %s
        ORDER BY ca.act_name, ca.section_number
        """,
        (case_number,),
    )


def reports_save_section_report(case_number: str, total: int, unique: int,
                                 deprecated: int, unmapped: int, era: str,
                                 quality_score: float) -> bool:
    """Persist citation audit report to case_section_reports."""
    return _w(
        """
        INSERT INTO case_section_reports
            (case_number, total_citations, unique_sections, deprecated_count,
             unmapped_count, document_era, has_deprecated_citations,
             citation_quality_score, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON DUPLICATE KEY UPDATE
            total_citations          = VALUES(total_citations),
            deprecated_count         = VALUES(deprecated_count),
            unmapped_count           = VALUES(unmapped_count),
            document_era             = VALUES(document_era),
            has_deprecated_citations = VALUES(has_deprecated_citations),
            citation_quality_score   = VALUES(citation_quality_score),
            created_at               = NOW()
        """,
        (case_number, total, unique, deprecated, unmapped, era,
         deprecated > 0, quality_score),
    )


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE: Translation  →  case_translations + sections
# ══════════════════════════════════════════════════════════════════════════════

def translation_get(case_number: str, language: str = "hi") -> Optional[Dict]:
    """Fetch stored translation for a case."""
    return _q(
        """
        SELECT ct.translated_text, ct.language, ct.translation_model, ct.created_at
        FROM case_translations ct
        JOIN cases c ON ct.case_id = c.case_id
        WHERE c.case_number = %s AND ct.language = %s
        ORDER BY ct.created_at DESC
        LIMIT 1
        """,
        (case_number, language),
        many=False,
    )


def translation_get_section(act: str, section: str, language: str = "hi") -> Optional[Dict]:
    """Fetch translated section text — joins case_translations to sections."""
    return _q(
        """
        SELECT s.act_name, s.section_number, s.title,
               ct.translated_text, ct.language
        FROM sections s
        LEFT JOIN case_translations ct
               ON ct.source_reference = CONCAT(s.act_name, '-', s.section_number)
               AND ct.language = %s
        WHERE s.act_name = %s AND s.section_number = %s
        LIMIT 1
        """,
        (language, act.upper(), section.strip()),
        many=False,
    )


def translation_save(case_id: int, translated_text: str,
                     language: str, model: str = "groq") -> bool:
    """Persist translation to case_translations."""
    return _w(
        """
        INSERT INTO case_translations
            (case_id, translated_text, language, translation_model, created_at)
        VALUES (%s, %s, %s, %s, NOW())
        ON DUPLICATE KEY UPDATE
            translated_text    = VALUES(translated_text),
            translation_model  = VALUES(translation_model),
            created_at         = NOW()
        """,
        (case_id, translated_text, language, model),
    )


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE: Chat Assistant  →  chat_history + cases + sections
# ══════════════════════════════════════════════════════════════════════════════

def chat_get_history(session_id: str, limit: int = 20) -> List[Dict]:
    """Fetch chat history for a session."""
    return _q(
        """
        SELECT role, message, created_at
        FROM chat_history
        WHERE session_id = %s
        ORDER BY created_at ASC
        LIMIT %s
        """,
        (session_id, limit),
    )


def chat_save_message(session_id: str, role: str, message: str,
                      case_number: str = None) -> bool:
    """Persist a chat message to chat_history."""
    return _w(
        """
        INSERT INTO chat_history
            (session_id, role, message, case_number, created_at)
        VALUES (%s, %s, %s, %s, NOW())
        """,
        (session_id, role, message[:4000], case_number),
    )


def chat_get_case_context(case_number: str) -> Optional[Dict]:
    """Pull case + section context to feed into chat assistant."""
    return _q(
        """
        SELECT c.case_number, c.case_type, c.court_name, c.filing_date,
               ecs.case_stage, ecs.next_hearing_date, ecs.judge_assigned,
               adr.recommended_adr, adr.lok_adalat_score
        FROM cases c
        LEFT JOIN ecourts_case_status ecs ON ecs.case_number = c.case_number
        LEFT JOIN adr_suitability adr     ON adr.case_number = c.case_number
        WHERE c.case_number = %s
        LIMIT 1
        """,
        (case_number,),
        many=False,
    )


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE: System Monitoring  →  system_logs + ecourts_sync_log
# ══════════════════════════════════════════════════════════════════════════════

def logs_get_recent_errors(limit: int = 50) -> List[Dict]:
    """Fetch recent error/warning entries from system_logs."""
    return _q(
        """
        SELECT log_level, module, message, created_at
        FROM system_logs
        WHERE log_level IN ('ERROR', 'WARNING', 'CRITICAL')
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (limit,),
    )


def logs_write(level: str, module: str, message: str) -> bool:
    """Write a log entry to system_logs."""
    return _w(
        """
        INSERT INTO system_logs (log_level, module, message, created_at)
        VALUES (%s, %s, %s, NOW())
        """,
        (level.upper(), module, message[:2000]),
    )


# ══════════════════════════════════════════════════════════════════════════════
# CROSS-FEATURE: Full Case Intelligence (multi-table join)
# ══════════════════════════════════════════════════════════════════════════════

def case_full_intelligence(case_number: str) -> Dict[str, Any]:
    """
    Aggregate complete intelligence for a case from all relevant tables.

    Tables queried:
      cases · ecourts_case_status · adr_suitability · case_section_reports
      case_predictions · similar_cases · case_summaries
    """
    # Core case record
    case = _q(
        """
        SELECT case_id, case_number, case_type, court_name,
               filing_date, document_era, has_deprecated_sections
        FROM cases WHERE case_number = %s LIMIT 1
        """,
        (case_number,), many=False,
    )

    case_id = (case or {}).get("case_id")

    # eCourts status
    ecourts = _q(
        """
        SELECT cnr_number, case_stage, next_hearing_date,
               judge_assigned, court_complex, last_synced_at
        FROM ecourts_case_status
        WHERE case_number = %s
        ORDER BY last_synced_at DESC LIMIT 1
        """,
        (case_number,), many=False,
    )

    # ADR assessment
    adr = _q(
        """
        SELECT recommended_adr, lok_adalat_score, is_lok_adalat_eligible,
               predicted_settlement_amount, predicted_days_to_settle
        FROM adr_suitability WHERE case_number = %s LIMIT 1
        """,
        (case_number,), many=False,
    )

    # BNS citation report
    bns_report = _q(
        """
        SELECT total_citations, deprecated_count, document_era,
               has_deprecated_citations, citation_quality_score
        FROM case_section_reports WHERE case_number = %s LIMIT 1
        """,
        (case_number,), many=False,
    )

    # Latest prediction
    prediction = _q(
        """
        SELECT cp.predicted_outcome, cp.conviction_probability, cp.risk_score
        FROM case_predictions cp
        WHERE cp.case_id = %s
        ORDER BY cp.created_at DESC LIMIT 1
        """,
        (case_id,), many=False,
    ) if case_id else None

    # Similar cases count
    similar_count_row = _q(
        "SELECT COUNT(*) AS cnt FROM similar_cases WHERE case_id = %s",
        (case_id,), many=False,
    ) if case_id else None
    similar_count = (similar_count_row or {}).get("cnt", 0)

    # Summary snippet
    summary = _q(
        """
        SELECT LEFT(summary_text, 300) AS summary_snippet
        FROM case_summaries WHERE case_id = %s
        ORDER BY created_at DESC LIMIT 1
        """,
        (case_id,), many=False,
    ) if case_id else None

    return {
        "case_number":  case_number,
        "case":         case,
        "ecourts":      ecourts,
        "adr":          adr,
        "bns_report":   bns_report,
        "prediction":   prediction,
        "similar_count": similar_count,
        "summary_snippet": (summary or {}).get("summary_snippet"),
    }


# ══════════════════════════════════════════════════════════════════════════════
# CROSS-FEATURE: Platform-wide MySQL stats (replaces MongoDB-based dashboard)
# ══════════════════════════════════════════════════════════════════════════════

def platform_stats() -> Dict[str, Any]:
    """
    Aggregate platform-wide statistics from MySQL tables only.
    Powers the intelligence dashboard.
    """
    def _count(table: str, where: str = "") -> int:
        row = _q(
            f"SELECT COUNT(*) AS n FROM {table}{' WHERE ' + where if where else ''}",
            many=False,
        )
        return int((row or {}).get("n", 0))

    return {
        "total_cases":               _count("cases"),
        "ecourts_cached":            _count("ecourts_case_status"),
        "adr_assessed":              _count("adr_suitability"),
        "lok_adalat_eligible":       _count("adr_suitability", "is_lok_adalat_eligible = TRUE"),
        "section_mappings":          _count("section_mapping"),
        "sections_in_db":            _count("sections"),
        "deprecated_citation_cases": _count("case_section_reports", "has_deprecated_citations = TRUE"),
        "predictions_stored":        _count("case_predictions"),
        "summaries_stored":          _count("case_summaries"),
        "similar_pairs":             _count("similar_cases"),
        "lok_adalat_awards":         _count("lok_adalat_awards"),
        "sync_log_entries":          _count("ecourts_sync_log"),
    }


# ══════════════════════════════════════════════════════════════════════════════
# WRITE HELPER: Similar Cases  →  similar_cases
# ══════════════════════════════════════════════════════════════════════════════

def similar_save(case_id: int, similar_case_id: int, score: float,
                 method: str = "embedding") -> bool:
    """
    Persist a semantic similarity pair to similar_cases.
    Called by the AI embedding pipeline after cosine-similarity ranking.
    Skips duplicate pairs gracefully via INSERT IGNORE.
    """
    return _w(
        """
        INSERT IGNORE INTO similar_cases
            (case_id, similar_case_id, similarity_score, method, created_at)
        VALUES (%s, %s, %s, %s, NOW())
        """,
        (case_id, similar_case_id, round(float(score), 6), method),
    )
