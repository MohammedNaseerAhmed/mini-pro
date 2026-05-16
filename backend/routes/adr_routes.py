"""
backend/routes/adr_routes.py

ADR suitability endpoints — real service calls, manual assessment,
Groq-powered draft generation, and live dashboard stats.
"""

import logging
import os
import re
from typing import Optional, List


from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.services.adr_suitability_service import (
    assess_adr, get_assessment, get_lok_adalat_eligible, get_adr_dashboard,
    classify_case_type, score_case, predict_settlement, estimate_complexity,
    is_criminal_case, store_assessment,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/adr", tags=["adr"])


# ── Pydantic Models ───────────────────────────────────────────────────────────

class ManualAssessRequest(BaseModel):
    case_number: Optional[str] = "MANUAL-ASSESS"
    case_type: Optional[str] = None          # motor_accident, consumer, labour, etc.
    dispute_amount: Optional[int] = None     # in INR
    dispute_years: Optional[float] = 1.0
    number_of_parties: Optional[int] = 2
    party_consent_level: Optional[str] = "Neutral"  # Both Willing, One Willing, Neutral, Unwilling
    case_description: Optional[str] = ""    # free text for AI classification


class DraftApplicationRequest(BaseModel):
    case_number: str
    draft_type: str = "lok_adalat"  # lok_adalat | arbitration_s8 | arbitration_s11
    case_details: Optional[str] = ""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _format_inr(amount: Optional[int]) -> str:
    if not amount:
        return "—"
    if amount >= 10_000_000:
        return f"₹{amount/10_000_000:.1f} Cr"
    if amount >= 100_000:
        return f"₹{amount/100_000:.1f}L"
    return f"₹{amount:,}"


async def _groq_draft_application(
    draft_type: str,
    case_number: str,
    assessment: dict,
    case_details: str,
) -> str:
    """Use Groq to generate a Lok Adalat referral or Arbitration petition."""
    try:
        import httpx
        groq_key = os.getenv("GROQ_API_KEY", "")
        groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        if not groq_key:
            return _fallback_draft(draft_type, case_number, assessment)

        case_type = assessment.get("case_type", "civil")
        settlement = _format_inr(assessment.get("predicted_settlement_amount"))
        days = assessment.get("predicted_days_to_settle", 90)
        recommended = assessment.get("recommended_adr", "lok_adalat")

        if draft_type == "lok_adalat":
            prompt = f"""Draft a formal APPLICATION FOR REFERENCE TO LOK ADALAT under Section 20 of the Legal Services Authorities Act, 1987.

Case Number: {case_number}
Case Type: {case_type}
Estimated Settlement: {settlement}
Predicted Resolution: {days} days

Additional Details: {case_details or 'Not provided'}

Include:
1. Court heading (IN THE COURT OF THE DISTRICT LEGAL SERVICES AUTHORITY)
2. In the matter of: [Petitioner] vs [Respondent]
3. APPLICATION UNDER SECTION 20 OF THE LEGAL SERVICES AUTHORITIES ACT, 1987
4. Respectfully Submitted By section
5. Facts of the case (short)
6. Grounds for reference to Lok Adalat
7. Prayer clause
8. Verification

Write a professional, complete draft:"""
        elif draft_type == "arbitration_s8":
            prompt = f"""Draft an APPLICATION UNDER SECTION 8 OF THE ARBITRATION AND CONCILIATION ACT, 1996 (Reference to Arbitration).

Case Number: {case_number}
Case Type: {case_type}
Case Details: {case_details or 'Commercial dispute with arbitration clause in agreement'}

Include:
1. Court heading
2. Case title
3. APPLICATION UNDER SECTION 8, ARBITRATION & CONCILIATION ACT, 1996
4. Brief facts
5. Existence of arbitration clause
6. Prayer to refer to arbitration
7. Verification

Write a professional, complete draft:"""
        else:  # arbitration_s11
            prompt = f"""Draft a PETITION UNDER SECTION 11 OF THE ARBITRATION AND CONCILIATION ACT, 1996 (Appointment of Arbitrator).

Case Number: {case_number}
Case Type: {case_type}
Case Details: {case_details or 'Commercial dispute requiring arbitrator appointment'}

Include:
1. High Court heading
2. Case title
3. PETITION UNDER SECTION 11(6), ARBITRATION & CONCILIATION ACT, 1996
4. Brief facts and failure of opposing party to appoint arbitrator
5. Prayer for appointment
6. Verification

Write a professional, complete draft:"""

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={
                    "model": groq_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1500,
                    "temperature": 0.2,
                },
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.warning("[ADR] Draft generation failed: %s", exc)

    return _fallback_draft(draft_type, case_number, assessment)


def _fallback_draft(draft_type: str, case_number: str, assessment: dict) -> str:
    case_type = assessment.get("case_type", "civil").replace("_", " ").title()
    if draft_type == "lok_adalat":
        return f"""IN THE COURT OF THE DISTRICT LEGAL SERVICES AUTHORITY

IN THE MATTER OF:
[Petitioner Name] ... PETITIONER
                    vs.
[Respondent Name] ... RESPONDENT

CASE NUMBER: {case_number}

APPLICATION UNDER SECTION 20 OF THE LEGAL SERVICES AUTHORITIES ACT, 1987
FOR REFERENCE TO LOK ADALAT

Respectfully Submitted by the Petitioner:

1. The Petitioner humbly submits that the above case is pending before this Hon'ble Court.

2. The nature of the dispute is: {case_type}.

3. The Petitioner believes that the dispute is suitable for resolution through Lok Adalat as:
   (a) The matter is compoundable in nature.
   (b) Both parties are willing to explore an amicable settlement.
   (c) Resolution through Lok Adalat would save time and costs for both parties.

4. The Petitioner therefore prays that this Hon'ble Court may be pleased to refer the above matter to the Lok Adalat for settlement under Section 20 of the Legal Services Authorities Act, 1987.

PRAYER:
It is therefore prayed that this Hon'ble Authority may be pleased to:
(a) Refer the above dispute to the Lok Adalat for settlement.
(b) Fix a date for the Lok Adalat proceedings.
(c) Pass such other orders as this Hon'ble Authority deems fit.

Date: ___________                        Petitioner / Advocate

VERIFICATION
I, [Name], the Petitioner above, do hereby verify that the contents of this application are true and correct to the best of my knowledge and belief.

Date: ___________                        Signature"""
    return f"[Application draft for {draft_type} — Case {case_number}]"


def _enrich_assessment(a: dict) -> dict:
    """Add formatted display fields to an assessment dict."""
    if not a:
        return a
    a["settlement_formatted"] = _format_inr(a.get("predicted_settlement_amount"))
    raw_pct = a.get("predicted_settlement_pct")
    a["settlement_pct_display"] = f"{round(raw_pct * 100)}%" if raw_pct else "—"
    days = a.get("predicted_days_to_settle")
    a["timeline_display"] = f"{days} days" if days else "—"

    # Settlement band (±25%)
    amt = a.get("predicted_settlement_amount")
    if amt:
        low = int(amt * 0.75)
        high = int(amt * 1.25)
        a["settlement_range"] = f"{_format_inr(low)} – {_format_inr(high)}"
    else:
        a["settlement_range"] = "—"

    # Rejection risk
    score = a.get("lok_adalat_score", 0)
    if score >= 75:
        a["rejection_risk"] = "High risk: Rejecting ADR likely means 5-10+ years in court with 3-5× higher costs."
    elif score >= 55:
        a["rejection_risk"] = "Moderate risk: Trial may take 3-7 years. Settlement terms likely worse at trial."
    else:
        a["rejection_risk"] = "Low risk: Case complexity may warrant full trial proceedings."

    # SLSA guidance
    ct = a.get("case_type", "civil")
    if ct in ("motor_accident", "consumer", "cheque_bounce", "municipal"):
        a["authority"] = "District Legal Services Authority (DLSA) — Permanent Lok Adalat"
    elif ct in ("labour",):
        a["authority"] = "State Legal Services Authority (SLSA) — Labour Lok Adalat"
    elif ct in ("matrimonial",):
        a["authority"] = "Family Court Mediation Centre / DLSA"
    elif ct in ("commercial", "property"):
        a["authority"] = "High Court Arbitration Centre / Commercial Court"
    else:
        a["authority"] = "District Legal Services Authority (DLSA)"

    return a


# ── Case-number validation ────────────────────────────────────────────────────

_ADR_PARTIAL_RE = re.compile(
    r"""
    ^ [A-Z]{1,3} $          |   # lone state/type code: "T", "TS", "MH"
    ^ [A-Z]{1,6} /? $       |   # type only: "OS", "OS/"
    ^ .{1,4} $                  # less than 5 meaningful chars
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _validate_adr_case_number(raw: str) -> str:
    cleaned = raw.strip().upper().replace(" ", "")
    if not cleaned or len(cleaned) < 5:
        raise HTTPException(
            status_code=400,
            detail="Case number is too short or empty. Enter a complete case number.",
        )
    if _ADR_PARTIAL_RE.match(cleaned):
        raise HTTPException(
            status_code=400,
            detail=f"'{raw.strip()}' is an incomplete case number. Enter the full reference.",
        )
    return cleaned


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/suitability/{case_number:path}")
def get_suitability(case_number: str):
    """
    Return stored ADR suitability assessment for a case.
    Falls back to a mock if not yet assessed.
    """
    cleaned = _validate_adr_case_number(case_number)
    data = get_assessment(cleaned)
    if data:
        return _enrich_assessment(dict(data))

    # Not yet in DB — return a clear "not assessed" response
    raise HTTPException(
        status_code=404,
        detail="ADR assessment not found. Upload a document first, or use /adr/assess for manual assessment."
    )



@router.post("/assess")
def manual_assess(req: ManualAssessRequest):
    """
    Perform a real-time ADR assessment from manual user input.
    No document upload required.
    """
    text = req.case_description or ""
    metadata = {
        "case_type": req.case_type,
        "dispute_amount": req.dispute_amount,
        "dispute_years": req.dispute_years or 1.0,
        "number_of_parties": req.number_of_parties or 2,
        "party_consent_level": req.party_consent_level or "Neutral",
    }

    result = assess_adr(
        case_number=req.case_number or "MANUAL-ASSESS",
        metadata=metadata,
        text=text,
        case_id=None,
        ecourts_data=None,
    )
    return _enrich_assessment(result)


@router.post("/draft-application")
async def draft_application(req: DraftApplicationRequest):
    """
    Generate a Lok Adalat referral application (Section 20 LSAA)
    or Arbitration petition (Section 8 / Section 11) via Groq AI.
    """
    valid_types = ("lok_adalat", "arbitration_s8", "arbitration_s11")
    if req.draft_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"draft_type must be one of: {valid_types}")

    # Try to fetch stored assessment for context
    assessment = get_assessment(req.case_number) or {}
    if not assessment:
        assessment = {
            "case_type": "civil",
            "predicted_settlement_amount": None,
            "predicted_days_to_settle": 90,
            "recommended_adr": req.draft_type.replace("_s8", "").replace("_s11", ""),
        }

    draft_text = await _groq_draft_application(
        req.draft_type, req.case_number, dict(assessment), req.case_details or ""
    )

    return {
        "case_number": req.case_number,
        "draft_type": req.draft_type,
        "draft": draft_text,
        "authority": _enrich_assessment(dict(assessment)).get("authority", "DLSA"),
        "legal_basis": {
            "lok_adalat": "Section 20, Legal Services Authorities Act, 1987",
            "arbitration_s8": "Section 8, Arbitration & Conciliation Act, 1996",
            "arbitration_s11": "Section 11(6), Arbitration & Conciliation Act, 1996",
        }.get(req.draft_type, ""),
    }


@router.get("/eligible-cases")
def eligible_cases(limit: int = Query(default=20, le=50)):
    """List cases eligible for Lok Adalat, highest score first."""
    rows = get_lok_adalat_eligible(limit)
    return {"cases": rows, "count": len(rows)}


@router.get("/dashboard-stats")
def get_adr_dashboard_stats():
    """Aggregate ADR statistics for the dashboard panel."""
    stats = get_adr_dashboard()
    # Ensure numeric fields are JSON-safe
    clean = {}
    for k, v in (stats or {}).items():
        try:
            clean[k] = float(v) if v is not None else 0
        except (TypeError, ValueError):
            clean[k] = v
    return clean or {
        "total_assessed": 0,
        "lok_adalat_eligible": 0,
        "avg_lok_adalat_score": 0,
        "recommended_lok_adalat": 0,
        "recommended_mediation": 0,
        "recommended_arbitration": 0,
        "recommended_court": 0,
    }
