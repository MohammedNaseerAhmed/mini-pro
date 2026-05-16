"""
backend/services/section_mapper_service.py

IPC / CrPC / IEA  →  BNS / BNSS / BSA section mapper.
MySQL is the single source of truth — NO JSON files, NO hardcoded mappings.

Tables used:
  sections        — full section text for all 6 acts
  section_mapping — bidirectional cross-act mappings
"""

import logging
import re
from typing import Any, Dict, List, Optional

from backend.database.mysql import get_mysql_connection
from backend.database.mongo import get_db, is_mongo_connected

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Recognised act abbreviations
# ---------------------------------------------------------------------------
OLD_ACTS = {"IPC", "CrPC", "IEA"}
NEW_ACTS = {"BNS", "BNSS", "BSA"}
ALL_ACTS  = OLD_ACTS | NEW_ACTS

# ---------------------------------------------------------------------------
# Advanced regex patterns for citation extraction
# ---------------------------------------------------------------------------
SECTION_PATTERNS = [
    # "Section 302 IPC" / "Section 438 CrPC"
    (r'\bSection[s]?\s+(\d+[A-Za-z]?(?:\(\d+\))?)\s+I\.?P\.?C\.?', 'IPC'),
    (r'\bSection[s]?\s+(\d+[A-Za-z]?(?:\(\d+\))?)\s+Cr\.?P\.?C\.?', 'CrPC'),
    (r'\bSection[s]?\s+(\d+[A-Za-z]?(?:\(\d+\))?)\s+I\.?E\.?A\.?', 'IEA'),
    (r'\bSection[s]?\s+(\d+[A-Za-z]?(?:\(\d+\))?)\s+B\.?N\.?S\.?S\.?', 'BNSS'),
    (r'\bSection[s]?\s+(\d+[A-Za-z]?(?:\(\d+\))?)\s+B\.?N\.?S\.?(?!S)', 'BNS'),
    (r'\bSection[s]?\s+(\d+[A-Za-z]?(?:\(\d+\))?)\s+B\.?S\.?A\.?', 'BSA'),
    # "Section 302 of IPC" / full act name
    (r'\bSection[s]?\s+(\d+[A-Za-z]?(?:\(\d+\))?)\s+of\s+(?:the\s+)?I\.?P\.?C\.?|Indian Penal Code', 'IPC'),
    (r'\bSection[s]?\s+(\d+[A-Za-z]?)\s+of\s+(?:the\s+)?Cr\.?P\.?C\.?|Code of Criminal Procedure', 'CrPC'),
    (r'\bSection[s]?\s+(\d+[A-Za-z]?)\s+of\s+(?:the\s+)?(?:Indian\s+)?Evidence Act', 'IEA'),
    (r'\bSection[s]?\s+(\d+[A-Za-z]?(?:\(\d+\))?)\s+of\s+(?:the\s+)?B\.?N\.?S\.?|Bharatiya Nyaya Sanhita', 'BNS'),
    # "IPC Section 302" / "IPC 302"
    (r'\bIPC\s+[Ss](?:ection[s]?)?\s*(\d+[A-Za-z]?(?:\(\d+\))?)', 'IPC'),
    (r'\bCrPC\s+[Ss](?:ection[s]?)?\s*(\d+[A-Za-z]?)', 'CrPC'),
    (r'\bBNSS\s+[Ss](?:ection[s]?)?\s*(\d+[A-Za-z]?)', 'BNSS'),
    (r'\bBSA\s+[Ss](?:ection[s]?)?\s*(\d+[A-Za-z]?)', 'BSA'),
    # "u/s 302 IPC" shorthand
    (r'\bu/s\s+(\d+[A-Za-z]?(?:\(\d+\))?)\s+I\.?P\.?C\.?', 'IPC'),
    (r'\bu/s\s+(\d+[A-Za-z]?(?:\(\d+\))?)\s+Cr\.?P\.?C\.?', 'CrPC'),
    (r'\bu/s\s+(\d+[A-Za-z]?(?:\(\d+\))?)\s+I\.?E\.?A\.?', 'IEA'),
    (r'\bu/s\s+(\d+[A-Za-z]?(?:\(\d+\))?)\s+B\.?N\.?S\.?', 'BNS'),
    (r'\bu/s\s+(\d+[A-Za-z]?(?:\(\d+\))?)\s+IPC', 'IPC'),
    # "BNS 101" standalone
    (r'\bBNS\s+(\d+[A-Za-z]?(?:\(\d+\))?)', 'BNS'),
]


# ===========================================================================
# Internal DB helpers
# ===========================================================================

def _run_query(sql: str, params: tuple) -> List[Dict[str, Any]]:
    """Execute a SELECT query and return rows as a list of dicts."""
    conn = None
    try:
        conn = get_mysql_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.close()
        return rows
    except Exception as exc:
        logger.error("MySQL query failed | sql=%s | params=%s | err=%s", sql, params, exc)
        return []
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def _fetch_section_details(act_name: str, section_number: str) -> Optional[Dict[str, Any]]:
    """
    Fetch full section details from the `sections` table.

    Returns a dict with keys: id, act_name, section_number, title,
    content, full_description, punishment  — or None if not found.
    """
    rows = _run_query(
        "SELECT * FROM sections WHERE act_name = %s AND section_number = %s LIMIT 1",
        (act_name.upper(), section_number.strip()),
    )
    return rows[0] if rows else None


def _mapping_row_to_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise a section_mapping DB row to a standard mapping dict."""
    return {
        "old_act":      row.get("old_act", ""),
        "old_section":  row.get("old_section", ""),
        "old_title":    row.get("old_title", ""),
        "new_act":      row.get("new_act", ""),
        "new_section":  row.get("new_section", ""),
        "new_title":    row.get("new_title", ""),
        "change_type":  row.get("change_type", "retained"),
        "change_notes": row.get("change_notes", ""),
    }


# ===========================================================================
# Public API
# ===========================================================================

def map_section(act: str, section: str) -> Optional[Dict[str, Any]]:
    """
    Bidirectional section lookup via MySQL.

    Fallback chain (no hallucination):
      1. Exact old→new match in section_mapping
      2. Exact new→old match in section_mapping
      3. Title-similarity search (LIKE) on old_title
      4. Return None — mapping not found

    Returns dict: {direction, mapping, details} or None.
    """
    act     = act.upper().strip()
    section = section.strip()

    # ── 1. Old → New exact match ──────────────────────────────────────────
    rows = _run_query(
        """
        SELECT sm.*, s.content, s.full_description, s.punishment, s.title AS section_detail_title
        FROM section_mapping sm
        LEFT JOIN sections s
               ON sm.new_section_id = s.id
        WHERE sm.old_act = %s AND sm.old_section = %s
        LIMIT 1
        """,
        (act, section),
    )
    if rows:
        row    = rows[0]
        mapping = _mapping_row_to_dict(row)
        details = {
            "content":          row.get("content", ""),
            "full_description": row.get("full_description", ""),
            "punishment":       row.get("punishment", ""),
        }
        return {"direction": "old_to_new", "mapping": mapping, "details": details}

    # ── 2. New → Old exact match ──────────────────────────────────────────
    rows = _run_query(
        """
        SELECT sm.*, s.content, s.full_description, s.punishment
        FROM section_mapping sm
        LEFT JOIN sections s
               ON sm.old_section_id = s.id
        WHERE sm.new_act = %s AND sm.new_section = %s
        LIMIT 1
        """,
        (act, section),
    )
    if rows:
        row     = rows[0]
        mapping = _mapping_row_to_dict(row)
        details = {
            "content":          row.get("content", ""),
            "full_description": row.get("full_description", ""),
            "punishment":       row.get("punishment", ""),
        }
        return {"direction": "new_to_old", "mapping": mapping, "details": details}

    # ── 3. Title-similarity fallback ──────────────────────────────────────
    result = _fallback_title_search(act, section)
    if result:
        return result

    return None


def _fallback_title_search(act: str, section: str) -> Optional[Dict[str, Any]]:
    """
    Fuzzy fallback: search section_mapping by old_title containing the
    section number as a keyword. Returns first hit or None.
    """
    rows = _run_query(
        """
        SELECT sm.*, s.content, s.full_description, s.punishment
        FROM section_mapping sm
        LEFT JOIN sections s ON sm.new_section_id = s.id
        WHERE sm.old_act = %s AND sm.old_title LIKE %s
        LIMIT 5
        """,
        (act, f"%{section}%"),
    )
    if not rows:
        return None
    row     = rows[0]
    mapping = _mapping_row_to_dict(row)
    details = {
        "content":          row.get("content", ""),
        "full_description": row.get("full_description", ""),
        "punishment":       row.get("punishment", ""),
    }
    return {"direction": "old_to_new_approx", "mapping": mapping, "details": details}


def search_by_keyword(query: str) -> List[Dict[str, Any]]:
    """
    Search section_mapping by keyword against old_title and new_title.
    Also searches sections.title as a secondary source.

    Returns list of enriched mapping dicts.
    """
    query = query.strip()
    if not query:
        return []

    like = f"%{query}%"

    rows = _run_query(
        """
        SELECT sm.*,
               s_new.content          AS new_content,
               s_new.full_description AS new_full_description,
               s_new.punishment       AS new_punishment
        FROM section_mapping sm
        LEFT JOIN sections s_new ON sm.new_section_id = s_new.id
        WHERE sm.old_title  LIKE %s
           OR sm.new_title  LIKE %s
        LIMIT 50
        """,
        (like, like),
    )

    results = []
    seen = set()
    for row in rows:
        uid = (row.get("old_act"), row.get("old_section"))
        if uid in seen:
            continue
        seen.add(uid)
        results.append({
            **_mapping_row_to_dict(row),
            "details": {
                "content":          row.get("new_content", ""),
                "full_description": row.get("new_full_description", ""),
                "punishment":       row.get("new_punishment", ""),
            },
        })

    # Secondary: search sections table directly
    if not results:
        sec_rows = _run_query(
            "SELECT * FROM sections WHERE title LIKE %s LIMIT 20",
            (like,),
        )
        for r in sec_rows:
            uid = (r.get("act_name"), r.get("section_number"))
            if uid not in seen:
                seen.add(uid)
                results.append({
                    "old_act":      r.get("act_name", ""),
                    "old_section":  r.get("section_number", ""),
                    "old_title":    r.get("title", ""),
                    "new_act":      "",
                    "new_section":  "",
                    "new_title":    "",
                    "change_type":  "unknown",
                    "change_notes": "",
                    "details": {
                        "content":          r.get("content", ""),
                        "full_description": r.get("full_description", ""),
                        "punishment":       r.get("punishment", ""),
                    },
                })

    return results


def get_section_details(act_name: str, section_number: str) -> Optional[Dict[str, Any]]:
    """
    Fetch full section details from the sections table.
    Exposed for direct use by routes.
    """
    return _fetch_section_details(act_name, section_number)


def extract_and_map_sections(case_number: str, text: str) -> Dict[str, Any]:
    """
    Extract all section citations from text, map each via MySQL,
    and return an analysis report.

    Also persists era/deprecation flags to MySQL cases table and Mongo.
    """
    found: List[Dict[str, Any]] = []
    seen: set = set()

    for pattern, act in SECTION_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            section = match.group(1).upper() if match.groups() else ""
            if not section:
                continue

            key = (act, section)
            if key in seen:
                continue
            seen.add(key)

            result  = map_section(act, section)
            mapping = result["mapping"] if result else None

            found.append({
                "act":       act,
                "section":   section,
                "mapped":    mapping is not None,
                "equivalent": mapping,
                "details":   result.get("details") if result else None,
                "direction": result.get("direction") if result else None,
                "raw_match": match.group(0).strip(),
            })

    # Era detection
    old_acts = {f["act"] for f in found if f["act"] in OLD_ACTS}
    new_acts = {f["act"] for f in found if f["act"] in NEW_ACTS}

    era = "pre_2024"
    if new_acts and not old_acts:
        era = "post_2024"
    elif new_acts and old_acts:
        era = "transitional"

    deprecated = [f for f in found if f["act"] in OLD_ACTS and f["mapped"]]

    report = {
        "sections_found":          found,
        "total":                   len(found),
        "mapped_count":            sum(1 for f in found if f["mapped"]),
        "document_era":            era,
        "deprecated_sections":     deprecated,
        "has_deprecated_citations": len(deprecated) > 0,
    }

    _update_cases_table(case_number, era, len(deprecated) > 0)
    _save_report_mongo(case_number, report)

    return report


def flag_deprecated_in_draft(draft_text: str) -> List[Dict[str, Any]]:
    """Flag deprecated IPC/CrPC/IEA citations in a draft text."""
    report = extract_and_map_sections("DRAFT", draft_text)
    flags  = []

    for item in report["deprecated_sections"]:
        m = item["equivalent"]
        flags.append({
            "deprecated":  f"{item['act']} {item['section']}",
            "use_instead": f"{m['new_act']} {m['new_section']}",
            "change_type": m.get("change_type", ""),
            "notes":       m.get("change_notes", ""),
            "raw_text":    item["raw_match"],
            "details":     item.get("details"),
        })
    return flags


# ---------------------------------------------------------------------------
# Similarity / normalization
# ---------------------------------------------------------------------------

def normalize_sections_for_similarity(text: str) -> str:
    """Replace old-act citations with canonical new-act forms for similarity scoring."""
    processed = text
    report    = extract_and_map_sections("NORM", text)

    for item in report["sections_found"]:
        canonical = None
        if item["mapped"]:
            m = item["equivalent"]
            canonical = f"{m['new_act']}-{m['new_section']}"
        elif item["act"] in NEW_ACTS:
            canonical = f"{item['act']}-{item['section']}"

        if canonical:
            processed = processed.replace(item["raw_match"], canonical)

    return processed


# ===========================================================================
# Internal persistence helpers
# ===========================================================================

def _update_cases_table(case_number: str, era: str, has_dep: bool) -> None:
    if case_number in ("DRAFT", "NORM"):
        return
    conn = None
    try:
        conn = get_mysql_connection()
        cur  = conn.cursor()
        cur.execute(
            "UPDATE cases SET document_era = %s, has_deprecated_sections = %s WHERE case_number = %s",
            (era, has_dep, case_number),
        )
        conn.commit()
        cur.close()
    except Exception as exc:
        logger.error("MySQL cases update failed for %s: %s", case_number, exc)
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def _save_report_mongo(case_number: str, report: dict) -> None:
    if case_number in ("DRAFT", "NORM"):
        return
    if not is_mongo_connected():
        return
    db = get_db()
    db["case_facts"].update_one(
        {"case_number": case_number},
        {"$set": {"section_mapping": report}},
        upsert=True,
    )


def get_case_report(case_number: str) -> Optional[Dict[str, Any]]:
    """Retrieve stored section mapping report from Mongo."""
    if not is_mongo_connected():
        return None
    doc = get_db()["case_facts"].find_one(
        {"case_number": case_number},
        {"section_mapping": 1},
    )
    return (doc or {}).get("section_mapping")
