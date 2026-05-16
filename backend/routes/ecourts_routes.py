"""
backend/routes/ecourts_routes.py

Endpoints for eCourts Live Sync.
Supports the CAPTCHA-aware flow + AI enrichment via Groq.
Also provides the AI Guide assistant and paste-and-analyse workflow.
"""

import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.services.ecourts_service import (
    get_captcha_for_sync, sync_with_captcha, get_stored_status,
    process_and_store_html,
)
from backend.services.ecourts_scraper import (
    init_ecourts_session, live_cnr_search, get_cached_case,
)
from backend.services.section_mapper_service import extract_and_map_sections
from backend.services.db_intelligence import (
    ecourts_upsert_status, ecourts_log_sync,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ecourts", tags=["ecourts-sync"])

# ── Pydantic Models ───────────────────────────────────────────────────────────

class CaptchaSyncRequest(BaseModel):
    case_number: str
    cnr_number: str
    captcha_code: str
    cookies: Dict[str, str]


class LiveSearchRequest(BaseModel):
    """
    Payload for POST /ecourts/live-search.
    Frontend sends this ONLY after:
      1. user has entered a complete CNR number
      2. user has solved the CAPTCHA from /ecourts/captcha
      3. user clicks Search
    Never sent while typing.
    """
    cnr_number:   str              # Full 16-char CNR — validated by backend
    captcha_code: str              # Text the user read from the CAPTCHA image
    cookies:      Dict[str, str]   # Session cookies from GET /ecourts/captcha


class GuideRequest(BaseModel):
    query: str          # Free-text user input e.g. "MHAU019999992015" or "my name is Sharma"


class PastedCaseRequest(BaseModel):
    pasted_text: str    # Raw text copy-pasted from eCourts portal
    case_number: Optional[str] = None   # Internal case reference (if known)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _compute_urgency(next_hearing_date: Optional[str]) -> Dict:
    """Return urgency metadata based on next hearing date."""
    if not next_hearing_date:
        return {"level": "unknown", "label": "No date set", "days": None}
    try:
        hd = datetime.strptime(str(next_hearing_date)[:10], "%Y-%m-%d")
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        days = (hd - today).days
        if days < 0:
            return {"level": "past", "label": "Hearing date passed", "days": days}
        if days <= 3:
            return {"level": "critical", "label": f"⚠ In {days} day(s)!", "days": days}
        if days <= 7:
            return {"level": "high", "label": f"In {days} days", "days": days}
        if days <= 30:
            return {"level": "medium", "label": f"In {days} days", "days": days}
        return {"level": "low", "label": f"In {days} days", "days": days}
    except Exception:
        return {"level": "unknown", "label": str(next_hearing_date), "days": None}


async def _generate_ai_summary(data: Dict) -> str:
    """Call Groq to generate a plain-language case summary."""
    try:
        import httpx
        groq_key = os.getenv("GROQ_API_KEY", "")
        groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        if not groq_key:
            return ""

        hearing_date = data.get("next_hearing_date", "unknown")
        stage = data.get("case_stage", "unknown")
        judge = data.get("judge_assigned", "unknown")
        petitioner = data.get("petitioner_name", "unknown")
        respondent = data.get("respondent_name", "unknown")
        court = data.get("court_complex", "unknown")
        cnr = data.get("cnr_number", "")

        prompt = f"""You are a legal assistant. Summarize this case status in 2-3 plain sentences in English for a lawyer. Be direct and professional.

Case: {cnr}
Court: {court}
Stage: {stage}
Judge: {judge}
Petitioner: {petitioner}
Respondent: {respondent}
Next Hearing: {hearing_date}

Write the summary:"""

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={
                    "model": groq_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 200,
                    "temperature": 0.3,
                },
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.warning("[eCourts] AI summary failed: %s", exc)
    return ""


# ── CNR / Case Number Validation ────────────────────────────────────────────

_PARTIAL_DISCARD_RE = re.compile(
    r"""
    # Reject lone state-code fragments: "MH", "OS", "O", etc.
    ^ [A-Z]{1,3} $
    |
    # Reject only-slash or slash-prefixed single tokens: "OS/", "OS/1"
    ^ [A-Z]{1,6} /? \d{0,4} $
    |
    # Reject input that is obviously less than 5 meaningful chars after strip
    ^ .{1,4} $
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _validate_case_number(raw: str) -> str:
    """
    Normalize and validate a case_number / CNR before any DB/scraper work.
    Returns the cleaned string, or raises HTTPException(400) for partial inputs.
    """
    cleaned = raw.strip().upper().replace(" ", "")
    if not cleaned:
        raise HTTPException(status_code=400, detail="Case number cannot be empty.")
    if len(cleaned) < 5:
        raise HTTPException(
            status_code=400,
            detail=f"Case number '{raw.strip()}' is too short. Minimum 5 characters required. "
                   "Please enter a complete case number or 16-digit CNR.",
        )
    if _PARTIAL_DISCARD_RE.match(cleaned):
        raise HTTPException(
            status_code=400,
            detail=f"'{raw.strip()}' appears to be an incomplete case number. "
                   "Enter the full case number (e.g. OS/105/2024) or 16-digit CNR.",
        )
    return cleaned


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/status/{case_number:path}")
async def get_status(case_number: str):
    """Return stored case status from MySQL (with urgency metadata)."""
    cleaned = _validate_case_number(case_number)
    data = get_stored_status(cleaned)
    if not data:
        raise HTTPException(status_code=404, detail="No status linked for this case.")
    # Attach urgency
    data["urgency"] = _compute_urgency(data.get("next_hearing_date"))
    return data


# Alias: frontend may call /ecourts/case-status/ — map to same handler
@router.get("/case-status/{case_number:path}")
async def get_case_status_alias(case_number: str):
    """Alias for /status/ to support legacy frontend calls."""
    return await get_status(case_number)


# ── New Production Routes ─────────────────────────────────────────────────────

@router.get("/captcha")
async def get_captcha():
    """
    Step 1 — Initialize a real browser-like session with eCourts and return:
      - captcha_image: base64 PNG to display in the UI
      - cookies: session cookies to send back with /live-search

    Frontend MUST display this CAPTCHA to the user and wait for manual entry.
    DO NOT call this endpoint while the user is typing.
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = await loop.run_in_executor(pool, init_ecourts_session)

    if not result.get("success"):
        raise HTTPException(
            status_code=502,
            detail=result.get("error", "Failed to initialize eCourts session."),
        )
    return result


# ── CNR validation for live-search ───────────────────────────────────────────

_CNR_STRICT_RE = re.compile(r'^[A-Z]{4}\d{9,12}$')

def _validate_cnr_strict(raw: str) -> str:
    """
    Strict 16-char CNR validation for live-search.
    Accepts: MHPN010101234562021 (4 alpha + 9-12 digits)
    Also accepts: OS/131/2026 style case numbers (at least 8 chars with digit + slash)
    Rejects: partial inputs.
    """
    cleaned = raw.strip().upper().replace(" ", "").replace("-", "")
    if not cleaned:
        raise HTTPException(status_code=400, detail="CNR number cannot be empty.")

    # Allow CNR format (4 letters + 9-12 digits)
    if _CNR_STRICT_RE.match(cleaned):
        return cleaned

    # Also allow case-number format like OS/131/2026 (has slash + digit + year)
    if "/" in raw and re.search(r'\d{4}', raw):
        # Minimum: TYPE/NUMBER/YEAR e.g. OS/131/2026
        parts = raw.strip().split("/")
        if len(parts) == 3 and parts[2].isdigit() and len(parts[2]) == 4:
            return raw.strip().upper()

    # Reject partial inputs
    if len(cleaned) < 8:
        raise HTTPException(
            status_code=400,
            detail=f"'{raw.strip()}' is incomplete. Enter a full 16-digit CNR "
                   "(e.g. MHPN010101234562021) or case number (e.g. OS/131/2026)."
        )

    return cleaned


@router.post("/live-search")
async def live_search(req: LiveSearchRequest):
    """
    Step 2 — Production CNR live search.

    Flow:
      1. Validate CNR format (reject partials → 400)
      2. Check MySQL cache (return instantly if fresh < 24h)
      3. Run requests.Session scraper with user CAPTCHA
      4. Parse HTML, persist to MySQL
      5. Return structured JSON + urgency metadata

    Request body:
        { "cnr_number": "MHPN010101234562021", "captcha_code": "etlP55", "cookies": {...} }

    Never triggered by typing. Only called after explicit user action.
    """
    # ── Validate CNR ─────────────────────────────────────────────────────────
    cnr = _validate_cnr_strict(req.cnr_number)

    # ── Validate CAPTCHA presence ─────────────────────────────────────────────
    captcha = req.captcha_code.strip()
    if not captcha:
        raise HTTPException(status_code=400, detail="CAPTCHA code cannot be empty.")
    if len(captcha) < 4:
        raise HTTPException(
            status_code=400,
            detail="CAPTCHA code too short. Please re-read the image and enter all characters."
        )

    # ── Cache check (instant return if data is fresh) ─────────────────────────
    cached = get_cached_case(cnr)
    if cached:
        logger.info("[live-search] Returning cached result for %s", cnr)
        result = cached
        result["urgency"] = _compute_urgency(result.get("next_hearing_date"))
        result["ai_summary"] = await _generate_ai_summary(result)
        return result

    # ── Live scrape ───────────────────────────────────────────────────────────
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    logger.info("[live-search] Starting live scrape for CNR: %s", cnr)

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=1) as pool:
        scrape_result = await loop.run_in_executor(
            pool,
            lambda: live_cnr_search(cnr, captcha, req.cookies),
        )

    # ── Error from scraper ────────────────────────────────────────────────────
    if not scrape_result.get("success"):
        err = scrape_result.get("error", "Scraping failed.")
        # 400 for CAPTCHA / not-found errors, 502 for portal errors
        status = 400 if any(
            kw in err.lower() for kw in ("captcha", "not found", "invalid", "session")
        ) else 502
        raise HTTPException(status_code=status, detail=err)

    # ── Enrich with urgency + AI summary ─────────────────────────────────────
    scrape_result["urgency"]    = _compute_urgency(scrape_result.get("next_hearing_date"))
    scrape_result["ai_summary"] = await _generate_ai_summary(scrape_result)

    return scrape_result



@router.get("/init-sync")
async def init_sync():
    """Step 1 (legacy): Get CAPTCHA image and session cookies from eCourts. Use /captcha instead."""
    res = await get_captcha_for_sync()
    if "error" in res:
        raise HTTPException(status_code=502, detail=res["error"])
    return res


@router.post("/sync")
async def perform_sync(req: CaptchaSyncRequest):
    """Step 2: Sync using user-provided CAPTCHA code. Returns parsed case data + urgency + AI summary."""
    res = await sync_with_captcha(
        req.case_number, req.cnr_number, req.captcha_code, req.cookies
    )
    if "error" in res:
        status = 400 if "Invalid Captcha" in res["error"] else 502
        raise HTTPException(status_code=status, detail=res["error"])

    # Enrich with urgency and AI summary
    res["urgency"] = _compute_urgency(res.get("next_hearing_date"))
    res["ai_summary"] = await _generate_ai_summary(res)
    return res


@router.get("/ai-summary/{case_number:path}")
async def get_ai_summary(case_number: str):
    """Fetch stored status and generate a fresh AI summary for the case."""
    data = get_stored_status(case_number)
    if not data:
        raise HTTPException(status_code=404, detail="No case status found.")
    urgency = _compute_urgency(data.get("next_hearing_date"))
    ai_summary = await _generate_ai_summary(data)
    return {
        "case_number": case_number,
        "urgency": urgency,
        "ai_summary": ai_summary,
        "next_hearing_date": data.get("next_hearing_date"),
        "case_stage": data.get("case_stage"),
        "judge_assigned": data.get("judge_assigned"),
    }


# ── eCourts AI Guide ──────────────────────────────────────────────────────────

ECOURTS_URL = "https://services.ecourts.gov.in/ecourtindia_v6/"

_SEARCH_METHODS: Dict[str, Dict[str, Any]] = {
    "cnr": {
        "id": "cnr",
        "title": "CNR Number Search (Fastest — Recommended)",
        "icon": "🔢",
        "description": "16-digit CNR number uniquely identifies any case across India.",
        "steps": [
            f"Open {ECOURTS_URL}",
            "Click \"CNR Number\" in the left Search Menu.",
            "Type your 16-digit CNR number WITHOUT hyphens or spaces.",
            "Read the CAPTCHA image and type it in the \"Enter Captcha\" box.\n   Tip: Click 🔊 for audio or 🔄 to refresh if unclear.",
            "Click the blue \"Search\" button.",
            "The results show: status, next hearing date, judge, court, parties, and orders.",
        ],
        "tips": [
            "Save your CNR after this search — it is the fastest route for all future lookups.",
            "Do NOT use browser back / reload — use only the Reset/Search buttons on the page.",
            "Works best on Chrome or Firefox desktop.",
        ],
    },
    "case_number": {
        "id": "case_number",
        "title": "Case Status by Case Number",
        "icon": "📋",
        "description": "Use this when you know Case Type, Case Number, and Year but not the CNR.",
        "steps": [
            f"Open {ECOURTS_URL}",
            "Click \"Case Status\" in the left Search Menu.",
            "Select: State → District → Court Complex (all three required).",
            "Click the \"Case Number\" tab.",
            "Select Case Type from the dropdown (CC, CS, CRL, WP, etc.).",
            "Enter Case Number and Year of filing.",
            "Enter CAPTCHA and click \"Go\".",
            "Results show case history, orders, and next hearing date.",
        ],
        "tips": [
            "Note your CNR from the results for faster future lookups.",
            "High Court cases: use the respective High Court website — eCourts covers only District and Taluka courts.",
        ],
    },
    "party_name": {
        "id": "party_name",
        "title": "Search by Party Name",
        "icon": "👤",
        "description": "Use this when you only know your name or the opponent's name.",
        "steps": [
            f"Open {ECOURTS_URL}",
            "Click \"Case Status\" in the left Search Menu.",
            "Select State → District → Court Complex.",
            "Click the \"Party Name\" tab.",
            "Type the petitioner or respondent name (minimum 3 characters).",
            "Select case status: Pending / Disposed / Both.",
            "Enter CAPTCHA and click \"Go\".",
            "Identify your case from the list by case number and year.",
        ],
        "tips": [
            "Use the full legal name as it appears on court documents.",
            "If too many results appear, narrow down using Disposed/Pending filter.",
        ],
    },
    "fir": {
        "id": "fir",
        "title": "Search by FIR Number",
        "icon": "🚔",
        "description": "Use this for criminal cases where you have the FIR number and police station.",
        "steps": [
            f"Open {ECOURTS_URL}",
            "Click \"Case Status\" → Select State, District, Court Complex.",
            "Click the \"FIR Number\" tab.",
            "Enter Police Station name, FIR Number, and Year.",
            "Enter CAPTCHA and click \"Go\".",
        ],
        "tips": [
            "FIR number is printed on the FIR copy issued at the police station.",
            "Criminal cases use the court-assigned case number after chargesheeting.",
        ],
    },
    "advocate": {
        "id": "advocate",
        "title": "Search by Advocate Name",
        "icon": "⚖️",
        "description": "Use this if a lawyer wants to see all their listed cases.",
        "steps": [
            f"Open {ECOURTS_URL}",
            "Click \"Case Status\" → Select State, District, Court Complex.",
            "Click the \"Advocate\" tab.",
            "Type the advocate's name (minimum 3 characters).",
            "Filter by Pending / Disposed.",
            "Enter CAPTCHA and click \"Go\".",
            "All cases where that advocate is listed will appear.",
        ],
        "tips": [
            "Use the Bar Council enrollment name for accurate results.",
        ],
    },
    "act_section": {
        "id": "act_section",
        "title": "Search by Act / Section",
        "icon": "📖",
        "description": "Find all cases filed under a specific IPC/BNS/CrPC section in a court.",
        "steps": [
            f"Open {ECOURTS_URL}",
            "Click \"Case Status\" → Select State, District, Court Complex.",
            "Click the \"Act\" tab.",
            "Select the Act from dropdown (IPC, BNS, CrPC, BNSS, etc.).",
            "Enter the section number.",
            "Enter CAPTCHA and click \"Go\".",
        ],
        "tips": [
            "This is useful for bulk research — e.g., find all cases under IPC 420 in a district.",
        ],
    },
}


def _detect_method(query: str) -> Dict[str, Any]:
    """
    Rule-based intent detection.
    Returns: {method_id, detected_value, confidence}
    """
    q = query.strip()

    # CNR: 16-alphanumeric chars, usually starts with state code
    cnr_match = re.search(r'\b([A-Z]{2}[A-Z0-9]{2}\d{9,12}\d*)\b', q.upper())
    if cnr_match or re.search(r'\b[A-Z]{4}\d{9,}\b', q.upper()):
        return {"method": "cnr", "detected": (cnr_match.group(1) if cnr_match else ""), "confidence": "high"}

    # FIR keywords
    if re.search(r'\bfir\b|first information|police station|fir no|fir number', q, re.I):
        fir_match = re.search(r'(\d{1,6}/\d{4}|\d{3,6})', q)
        return {"method": "fir", "detected": fir_match.group(0) if fir_match else "", "confidence": "high"}

    # Advocate keywords
    if re.search(r'\badvocate|adv\.|lawyer|counsel|vakil|bar council\b', q, re.I):
        return {"method": "advocate", "detected": q, "confidence": "medium"}

    # Act/Section keywords
    if re.search(r'\b(ipc|bns|crpc|bnss|iea|bsa)\s*\d+|section\s+\d+', q, re.I):
        return {"method": "act_section", "detected": q, "confidence": "medium"}

    # Case number patterns: OS/105/2024  WP/2345/2023  CC No.34/2022
    case_match = re.search(r'\b([A-Z]{1,6})[/\s]+(\d{1,6})[/\s]+(\d{4})\b', q.upper())
    if case_match:
        return {
            "method": "case_number",
            "detected": case_match.group(0),
            "confidence": "high",
        }

    # Name-like input (contains common name indicators)
    if re.search(r'\bmy name|named|petitioner|respondent|v/s|versus|plaintiff|defendant\b', q, re.I):
        return {"method": "party_name", "detected": q, "confidence": "medium"}

    # Fallback: if it looks like a person's name (2–4 words, mostly alpha)
    words = q.split()
    if 2 <= len(words) <= 5 and all(w.replace('.', '').isalpha() for w in words):
        return {"method": "party_name", "detected": q, "confidence": "low"}

    # Default to case number method
    return {"method": "case_number", "detected": "", "confidence": "low"}


@router.post("/guide")
async def ecourts_guide(req: GuideRequest):
    """
    Intelligent eCourts search guide.
    Detects what information the user has and returns the appropriate
    step-by-step search instructions for the official eCourts portal.
    """
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    detection   = _detect_method(req.query)
    method_id   = detection["method"]
    method_info = _SEARCH_METHODS[method_id]

    return {
        "method":         method_id,
        "method_title":   method_info["title"],
        "method_icon":    method_info["icon"],
        "description":    method_info["description"],
        "steps":          method_info["steps"],
        "tips":           method_info["tips"],
        "portal_url":     ECOURTS_URL,
        "detected_value": detection["detected"],
        "confidence":     detection["confidence"],
        "all_methods":    [
            {"id": k, "title": v["title"], "icon": v["icon"], "description": v["description"]}
            for k, v in _SEARCH_METHODS.items()
        ],
        "post_search_tip": (
            "After your search, copy-paste the result text into the 'Analyze Pasted Data' "
            "box below to automatically: map IPC sections to BNS, check ADR eligibility, "
            "and save your CNR for future fast lookups."
        ),
    }


# ── Paste-and-Analyse ─────────────────────────────────────────────────────────

_CNR_RE    = re.compile(r'\b([A-Z]{2}[A-Z0-9]{2}\d{9,15})\b')
_DATE_RE   = re.compile(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b')


def _extract_cnr(text: str) -> Optional[str]:
    m = _CNR_RE.search(text.upper())
    return m.group(1) if m else None


def _extract_next_date(text: str) -> Optional[str]:
    """Return first future-looking date mention."""
    dates = _DATE_RE.findall(text)
    return dates[-1] if dates else None


def _extract_parties(text: str) -> Dict[str, str]:
    """Simple heuristic: look for Petitioner/Respondent labels."""
    pet = re.search(r'Petitioner[s]?[:\s]+([A-Za-z .]+)', text)
    res = re.search(r'Respondent[s]?[:\s]+([A-Za-z .]+)', text)
    return {
        "petitioner": pet.group(1).strip()[:80] if pet else "",
        "respondent":  res.group(1).strip()[:80] if res else "",
    }



@router.post("/analyze-pasted")
async def analyze_pasted_case(req: PastedCaseRequest):
    """
    Accept text copy-pasted from the eCourts portal result page.
    Performs:
      1. CNR extraction
      2. Party name extraction
      3. Next hearing date extraction
      4. IPC → BNS / CrPC → BNSS section mapping
      5. ADR eligibility hint
      6. CNR + case number save to MySQL
    """
    text = req.pasted_text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Pasted text cannot be empty.")

    cnr          = _extract_cnr(text)
    parties      = _extract_parties(text)
    next_hearing = _extract_next_date(text)
    case_ref     = req.case_number or cnr or "PASTED"

    # BNS Section Mapping
    mapping_report = extract_and_map_sections(case_ref, text)

    # Save CNR to DB via intelligence layer
    cnr_saved = False
    if cnr and case_ref != "PASTED":
        cnr_saved = ecourts_upsert_status(
            case_number=case_ref,
            cnr=cnr,
            next_hearing=next_hearing,
            source="pasted",
        )
        if cnr_saved:
            ecourts_log_sync(cnr, "pasted", f"Saved from paste-and-analyse for {case_ref}")

    # Urgency from hearing date
    urgency = _compute_urgency(next_hearing)

    # ADR hint based on sections found
    civil_keywords = {"cheque", "property", "cheating", "breach", "compensation", "damages", "rent", "matrimonial"}
    text_lower     = text.lower()
    adr_hint = "possible" if any(k in text_lower for k in civil_keywords) else "check-required"

    return {
        "cnr_number":      cnr,
        "cnr_saved":       cnr_saved,
        "case_reference":  case_ref,
        "parties":         parties,
        "next_hearing":    next_hearing,
        "urgency":         urgency,
        "section_mapping": {
            "total_sections":   mapping_report["total"],
            "mapped_count":     mapping_report["mapped_count"],
            "document_era":     mapping_report["document_era"],
            "deprecated_found": mapping_report["has_deprecated_citations"],
            "sections":         [
                {
                    "act":         s["act"],
                    "section":     s["section"],
                    "mapped":      s["mapped"],
                    "new_act":     (s["equivalent"] or {}).get("new_act"),
                    "new_section": (s["equivalent"] or {}).get("new_section"),
                    "new_title":   (s["equivalent"] or {}).get("new_title"),
                }
                for s in mapping_report["sections_found"]
            ],
        },
        "adr_eligibility_hint": adr_hint,
        "actions_taken": [
            "BNS section mapping completed" if mapping_report["total"] > 0 else "No sections detected",
            f"CNR {cnr} saved to database" if cnr_saved else "CNR not found in text — not saved",
            f"Next hearing: {next_hearing}" if next_hearing else "No hearing date detected",
        ],
        "next_steps": [
            "Review BNS section mappings below.",
            "Run ADR Suitability Check from the ADR Checker tab.",
            "Share the CNR with your advocate for quick future lookups.",
        ] if cnr else [
            "No CNR found — paste the full eCourts result page for best results.",
            "If sections are detected, BNS mapping is available below.",
        ],
    }
