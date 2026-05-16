"""
backend/routes/bns_routes.py

Endpoints for IPC → BNS mapping, FIR text analysis, and draft rewriting.
"""

import logging
import os
import re
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.services.section_mapper_service import (
    map_section, search_by_keyword, extract_and_map_sections,
    flag_deprecated_in_draft, get_case_report, get_section_details
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bns", tags=["bns-mapper"])


# ── Pydantic Models ───────────────────────────────────────────────────────────

class DraftRequest(BaseModel):
    draft_text: str
    draft_type: Optional[str] = "petition"


class AnalyzeTextRequest(BaseModel):
    text: str
    case_number: Optional[str] = "DRAFT"


class RewriteDraftRequest(BaseModel):
    draft_text: str
    draft_type: Optional[str] = "petition"


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _groq_rewrite(original: str, flags: List[dict]) -> str:
    """Use Groq to rewrite a draft replacing deprecated sections with BNS equivalents."""
    if not flags:
        return original

    try:
        import httpx
        groq_key = os.getenv("GROQ_API_KEY", "")
        groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        if not groq_key:
            return _simple_rewrite(original, flags)

        changes = "\n".join(
            f"  - Replace '{f['deprecated']}' with '{f['use_instead']}' ({f['change_type']})"
            for f in flags[:20]
        )
        prompt = f"""You are a legal document editor. Rewrite the following legal draft by replacing all deprecated IPC/CrPC/IEA sections with their BNS/BNSS/BSA equivalents. Only substitute sections — do not change anything else.

Required substitutions:
{changes}

Original draft:
\"\"\"
{original[:3000]}
\"\"\"

Return ONLY the rewritten draft with no explanation:"""

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={
                    "model": groq_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 2000,
                    "temperature": 0.1,
                },
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.warning("[BNS] Groq rewrite failed: %s", exc)

    return _simple_rewrite(original, flags)


def _simple_rewrite(text: str, flags: List[dict]) -> str:
    """Fallback: regex-replace deprecated citations in place."""
    result = text
    for f in flags:
        old = f["deprecated"]        # e.g. "IPC 302"
        new = f["use_instead"]       # e.g. "BNS 101"
        # Match variations: "IPC 302", "Section 302 IPC", "u/s 302 IPC"
        patterns = [
            (rf'\b{re.escape(old)}\b', new),
            (rf'\bSection\s+{re.escape(old.split()[-1])}\s+{re.escape(old.split()[0])}\b',
             f"Section {new.split()[-1]} {new.split()[0]}"),
        ]
        for pat, repl in patterns:
            result = re.sub(pat, repl, result, flags=re.IGNORECASE)
    return result


def _highlight_substitutions(original: str, rewritten: str, flags: List[dict]) -> List[dict]:
    """Build a list of substitution diffs for the UI."""
    subs = []
    for f in flags:
        subs.append({
            "from": f["deprecated"],
            "to": f["use_instead"],
            "change_type": f["change_type"],
            "notes": f.get("notes", ""),
        })
    return subs


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/lookup")
def lookup_section(
    act: str = Query(..., description="IPC, CrPC, IEA, BNS, BNSS, or BSA"),
    section: str = Query(..., description="Section number"),
):
    """
    Bidirectional lookup: old act ↔ new act.
    Returns structured response with old_section, mapped_section, and full details
    sourced entirely from MySQL (section_mapping + sections tables).
    """
    res = map_section(act, section)
    if not res:
        raise HTTPException(
            status_code=404,
            detail=f"No mapping found for {act} {section}. Verify the section exists in the database."
        )

    mapping = res["mapping"]
    details = res.get("details") or {}

    return {
        "old_section": {
            "act":     mapping["old_act"],
            "section": mapping["old_section"],
            "title":   mapping.get("old_title", ""),
        },
        "mapped_section": {
            "act":         mapping["new_act"],
            "section":     mapping["new_section"],
            "title":       mapping.get("new_title", ""),
            "change_type": mapping.get("change_type", "retained"),
            "change_notes": mapping.get("change_notes", ""),
        },
        "details": {
            "content":          details.get("content", ""),
            "punishment":       details.get("punishment", ""),
            "full_description": details.get("full_description", ""),
        },
        "direction": res["direction"],
    }


@router.get("/section-details")
def section_details(
    act: str = Query(..., description="Act name: IPC, BNS, CrPC, BNSS, IEA, BSA"),
    section: str = Query(..., description="Section number, e.g. 420"),
):
    """
    Fetch full section text directly from the `sections` MySQL table.
    Returns title, content, punishment, and full_description.
    """
    details = get_section_details(act, section)
    if not details:
        raise HTTPException(
            status_code=404,
            detail=f"Section {act} {section} not found in the sections table."
        )
    return {
        "act":              details.get("act_name", act),
        "section":          details.get("section_number", section),
        "title":            details.get("title", ""),
        "content":          details.get("content", ""),
        "punishment":       details.get("punishment", ""),
        "full_description": details.get("full_description", ""),
    }


@router.get("/search")
def search_mappings(q: str = Query(..., min_length=2)):
    """Search mappings by keyword (e.g. 'murder', 'bail', 'rape') via MySQL LIKE query."""
    results = search_by_keyword(q)
    return {"results": results, "count": len(results)}


@router.get("/case-report/{case_number:path}")
def case_bns_report(case_number: str):
    """Retrieve stored BNS section audit report for a processed case."""
    report = get_case_report(case_number)
    if not report:
        raise HTTPException(status_code=404, detail="No BNS report found for this case.")
    return {"case_number": case_number, "report": report}


@router.post("/check-draft")
def check_draft(req: DraftRequest):
    """Check a draft petition for deprecated IPC/CrPC/IEA citations."""
    flags = flag_deprecated_in_draft(req.draft_text)
    return {
        "flags": flags,
        "flag_count": len(flags),
        "is_ready_for_filing": len(flags) == 0,
        "advice": (
            f"Found {len(flags)} deprecated citation(s). Replace with BNS/BNSS/BSA equivalents before filing."
            if flags else "All citations comply with post-July 2024 legislation. Ready for filing."
        ),
    }


@router.post("/analyze-text")
def analyze_text(req: AnalyzeTextRequest):
    """
    Extract ALL legal section citations from a text (FIR, petition, judgment)
    and map each to its BNS/BNSS/BSA equivalent with change flags.
    """
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    report = extract_and_map_sections(req.case_number or "DRAFT", req.text)

    # Build enriched section list
    enriched = []
    for item in report.get("sections_found", []):
        eq = item.get("equivalent") or {}
        enriched.append({
            "act": item["act"],
            "section": item["section"],
            "raw_match": item.get("raw_match", ""),
            "is_deprecated": item["act"] in ("IPC", "CrPC", "IEA") and item["mapped"],
            "mapped": item["mapped"],
            "new_act": eq.get("new_act"),
            "new_section": eq.get("new_section"),
            "new_title": eq.get("new_title"),
            "old_title": eq.get("old_title"),
            "change_type": eq.get("change_type"),
            "change_notes": eq.get("change_notes"),
        })

    deprecated_count = sum(1 for s in enriched if s["is_deprecated"])
    unmapped_count = sum(1 for s in enriched if not s["mapped"])

    return {
        "case_number": req.case_number,
        "sections_found": enriched,
        "total_sections": len(enriched),
        "deprecated_count": deprecated_count,
        "unmapped_count": unmapped_count,
        "document_era": report.get("document_era", "unknown"),
        "has_deprecated_citations": deprecated_count > 0,
        "advice": (
            f"⚠ {deprecated_count} deprecated section(s) found. Update before filing."
            if deprecated_count > 0
            else "✓ All citations are current. Document is compliant."
        ),
    }


@router.post("/rewrite-draft")
async def rewrite_draft(req: RewriteDraftRequest):
    """
    Rewrite a draft petition/FIR replacing all deprecated IPC/CrPC/IEA
    citations with BNS/BNSS/BSA equivalents. Returns original, rewritten
    text, and a substitution diff list.
    """
    if not req.draft_text or not req.draft_text.strip():
        raise HTTPException(status_code=400, detail="Draft text cannot be empty.")

    flags = flag_deprecated_in_draft(req.draft_text)

    if not flags:
        return {
            "original": req.draft_text,
            "rewritten": req.draft_text,
            "substitutions": [],
            "substitution_count": 0,
            "is_compliant": True,
            "message": "No changes needed — document is already BNS-compliant.",
        }

    rewritten = await _groq_rewrite(req.draft_text, flags)
    substitutions = _highlight_substitutions(req.draft_text, rewritten, flags)

    return {
        "original": req.draft_text,
        "rewritten": rewritten,
        "substitutions": substitutions,
        "substitution_count": len(substitutions),
        "is_compliant": False,
        "message": f"{len(substitutions)} section(s) updated to BNS/BNSS/BSA. Review highlighted changes before filing.",
    }
