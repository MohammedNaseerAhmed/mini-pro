"""
backend/services/adr_suitability_service.py

ADR Suitability Checker & Lok Adalat Outcome Predictor.

Responsibilities:
  1. Score a case on 4 ADR pathways (0-100): Lok Adalat, Mediation, Arbitration, Negotiation.
  2. Determine Lok Adalat eligibility per Legal Services Authorities Act 1987.
  3. Predict settlement amount using historical NALSA data from lok_adalat_awards table.
  4. Store the assessment in adr_suitability table.
  5. Expose lookup helpers for the /adr/* endpoints.
"""

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.database.mongo import get_db, is_mongo_connected
from backend.database.mysql import get_mysql_connection

logger = logging.getLogger(__name__)

# Path to weights file
WEIGHTS_PATH = os.path.join("backend", "data", "adr_weights.json")

def load_weights():
    if not os.path.exists(WEIGHTS_PATH):
        logger.warning("ADR weights file not found at %s. Using internal defaults.", WEIGHTS_PATH)
        return {}
    try:
        with open(WEIGHTS_PATH, "r") as f:
            return json.load(f)
    except Exception as exc:
        logger.error("Failed to load ADR weights: %s", exc)
        return {}

# ── Case-type classification ──────────────────────────────────────────────────

_CASE_TYPE_KEYWORDS: Dict[str, List[str]] = {
    "motor_accident":  ["motor", "accident", "vehicle", "mact", "rash driving", "compensation", "tribunal"],
    "consumer":        ["consumer", "complaint", "defective", "service deficiency", "forum"],
    "labour":          ["labour", "labor", "employee", "wage", "salary", "workman", "industrial"],
    "cheque_bounce":   ["cheque", "dishonour", "negotiable instrument", "138 ni"],
    "matrimonial":     ["marriage", "divorce", "custody", "maintenance", "alimony", "matrimonial"],
    "property":        ["property", "land", "tenant", "landlord", "eviction", "possession", "title"],
    "commercial":      ["contract", "commercial", "trade", "goods", "supply", "invoice", "arbitration"],
    "revenue":         ["revenue", "tax", "municipal", "panchayat", "assessment"],
    "municipal":       ["municipal", "corporation", "building", "permission", "licence"],
    "civil":           ["civil", "damages", "injunction", "declaration", "specific performance"],
}

_CRIMINAL_KEYWORDS = ["murder", "rape", "assault", "robbery", "dacoity", "kidnapping",
                      "extortion", "terrorism", "sedition", "pocso", "narcotic"]


def classify_case_type(text: str, existing_type: Optional[str] = None) -> str:
    """Return a canonical case type string."""
    if existing_type and existing_type.lower() not in ("unknown", "civil", ""):
        return existing_type.lower()
    text_lower = text.lower()
    best_type, best_count = "civil", 0
    for ctype, keywords in _CASE_TYPE_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in text_lower)
        if count > best_count:
            best_count, best_type = count, ctype
    return best_type


def is_criminal_case(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in _CRIMINAL_KEYWORDS)


def extract_dispute_amount(text: str) -> Optional[int]:
    """Try to extract a monetary claim amount from judgment text."""
    patterns = [
        r"(?:Rs\.?|rupees|amount of|claim(?:ed)? for|compensation of)\s*([\d,]+(?:\.\d+)?)\s*(?:lakhs?|lacs?)?",
        r"([\d,]+)\s*(?:/-|rupees|Rs\.?)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            raw = m.group(1).replace(",", "")
            try:
                amount = float(raw)
                # If "lakh" nearby, multiply
                if re.search(r"lakh|lac", text[max(0, m.start()-30):m.end()+30], re.IGNORECASE):
                    amount *= 100_000
                return int(amount)
            except ValueError:
                continue
    return None


def estimate_complexity(text: str, num_parties: int = 2) -> str:
    section_count = len(re.findall(r"\bS(?:ection)?\s+\d+", text))
    if section_count > 15 or num_parties > 4:
        return "Complex"
    if section_count > 6 or num_parties > 2:
        return "Moderate"
    return "Simple"


# ── Scoring algorithm ─────────────────────────────────────────────────────────

# Base scores (0-100) per case type per ADR pathway
_BASE_SCORES: Dict[str, Dict[str, int]] = {
    "motor_accident": {"lok_adalat": 88, "mediation": 70, "arbitration": 35, "negotiation": 60},
    "consumer":       {"lok_adalat": 82, "mediation": 75, "arbitration": 40, "negotiation": 65},
    "labour":         {"lok_adalat": 75, "mediation": 82, "arbitration": 55, "negotiation": 60},
    "cheque_bounce":  {"lok_adalat": 85, "mediation": 65, "arbitration": 30, "negotiation": 70},
    "matrimonial":    {"lok_adalat": 60, "mediation": 80, "arbitration": 20, "negotiation": 50},
    "property":       {"lok_adalat": 45, "mediation": 65, "arbitration": 72, "negotiation": 40},
    "commercial":     {"lok_adalat": 40, "mediation": 60, "arbitration": 85, "negotiation": 55},
    "revenue":        {"lok_adalat": 50, "mediation": 55, "arbitration": 30, "negotiation": 45},
    "municipal":      {"lok_adalat": 78, "mediation": 60, "arbitration": 25, "negotiation": 55},
    "civil":          {"lok_adalat": 62, "mediation": 68, "arbitration": 55, "negotiation": 50},
}
_DEFAULT_BASE = {"lok_adalat": 55, "mediation": 60, "arbitration": 50, "negotiation": 45}

_COMPLEXITY_MULT = {"Simple": 1.20, "Moderate": 1.00, "Complex": 0.72}

_CONSENT_DELTA = {
    "Both Willing": +15,
    "One Willing":  +5,
    "Neutral":       0,
    "Unwilling":   -20,
}

LOK_ADALAT_AMOUNT_LIMIT = 20_000_000  # Rs 2 crore upper limit per LSA guidelines


def _clamp(val: int) -> int:
    return max(0, min(100, val))


def score_case(
    case_type: str,
    complexity: str,
    consent: str,
    dispute_amount: Optional[int],
    dispute_years: float,
    num_parties: int,
    is_criminal: bool,
) -> Dict[str, Any]:
    """Core scoring function. Returns scores dict + metadata."""
    weights = load_weights()
    
    if is_criminal:
        # Criminal cases are almost never suitable for ADR
        return {
            "lok_adalat_score": 5, "mediation_score": 10,
            "arbitration_score": 5, "negotiation_score": 10,
            "recommended_adr": "court", "is_lok_adalat_eligible": False,
            "confidence_level": 0.95,
            "reasoning": "Criminal cases are not suitable for ADR under Indian law.",
        }

    base_map = weights.get("base_scores", {})
    base = base_map.get(case_type, base_map.get("default", {}))
    
    mult_map = weights.get("complexity_multipliers", {})
    mult = mult_map.get(complexity, 1.0)
    
    consent_map = weights.get("consent_deltas", {})
    c_delta = consent_map.get(consent, 0)

    factors = weights.get("other_factors", {})
    
    # Duration bonus
    duration_bonus = 0
    if dispute_years > factors.get("duration_bonus_threshold_years", 2):
        duration_bonus = min(
            factors.get("duration_bonus_max", 15),
            int(dispute_years * factors.get("duration_bonus_multiplier", 4))
        )

    # Multi-party penalty
    party_penalty = max(0, (num_parties - 2) * factors.get("party_penalty_multiplier", 8))

    # Amount impact
    amount_factor = 0
    if dispute_amount:
        if dispute_amount <= factors.get("small_dispute_threshold", 1000000):
            amount_factor = factors.get("small_dispute_bonus", 10)
        elif dispute_amount > factors.get("lok_adalat_amount_limit", 20000000):
            amount_factor = factors.get("large_dispute_penalty", -25)

    scores = {}
    for pathway, b in base.items():
        raw = int(b * mult) + c_delta + duration_bonus - party_penalty
        if pathway == "lok_adalat":
            raw += amount_factor
        scores[pathway] = _clamp(raw)

    # Recommendation
    threshold = 55
    sorted_pathways = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    recommended = "court"
    for pathway, s in sorted_pathways:
        if s >= threshold:
            recommended = pathway
            break

    lok_limit = factors.get("lok_adalat_amount_limit", 20000000)
    lok_eligible = (
        scores["lok_adalat"] >= 60
        and not is_criminal
        and (dispute_amount is None or dispute_amount <= lok_limit)
    )

    confidence = min(0.95, 0.50 + (scores[recommended] / 200) + (0.05 if dispute_years > 1 else 0))

    reasoning_parts = [
        f"Case type '{case_type}' base suitability: {base.get('lok_adalat', 55)}/100.",
        f"Complexity '{complexity}' mult: {mult:.2f}.",
    ]
    if c_delta != 0:
        reasoning_parts.append(f"Consent delta: {c_delta:+d}.")
    if duration_bonus:
        reasoning_parts.append(f"Duration bonus: +{duration_bonus}.")
    if amount_factor != 0:
        reasoning_parts.append(f"Amount adjustment: {amount_factor:+d}.")

    return {
        "lok_adalat_score":     scores["lok_adalat"],
        "mediation_score":      scores["mediation"],
        "arbitration_score":    scores["arbitration"],
        "negotiation_score":    scores["negotiation"],
        "recommended_adr":      recommended,
        "is_lok_adalat_eligible": lok_eligible,
        "confidence_level":     round(confidence, 2),
        "reasoning":            " ".join(reasoning_parts),
    }


def _adjournment_adjustment(ecourts_data: Optional[Dict[str, Any]]) -> Tuple[int, str]:
    """
    +15 if 4 or more of last 6 hearings are adjournments.
    -10 if stage indicates evidence/trial-final.
    """
    weights = load_weights()
    factors = weights.get("other_factors", {})
    
    if not ecourts_data:
        return 0, "No eCourts history available."
    history = ecourts_data.get("hearing_history") or []
    recent = history[:6]
    if not recent:
        return 0, "No recent hearing rows available."

    adjourned = 0
    for row in recent:
        row_text = " ".join(
            [
                str(row.get("purpose", "")),
                str(row.get("business", "")),
            ]
        ).lower()
        if "adjourn" in row_text or "next date" in row_text:
            adjourned += 1

    delta = 0
    if adjourned >= factors.get("adjournment_threshold_count", 4):
        delta = factors.get("adjournment_bonus", 15)
        
    reason = f"Adjournment pattern: {adjourned}/6 recent hearings."

    stage = str(ecourts_data.get("case_stage", "")).lower()
    if any(word in stage for word in ["evidence", "trial", "final"]):
        delta += factors.get("trial_stage_penalty", -10)
        reason += " Stage indicates evidence/trial; penalty applied."

    return delta, reason


# ── Settlement prediction ─────────────────────────────────────────────────────

def predict_settlement(
    case_type: str,
    dispute_amount: Optional[int],
    recommended_adr: str,
) -> Tuple[Optional[int], Optional[float], Optional[int]]:
    """
    Look up NALSA historical data and predict:
      - settlement amount
      - settlement percentage
      - days to settle
    Returns (amount, pct, days)
    """
    conn = None
    try:
        conn = get_mysql_connection()
        cur  = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT * FROM lok_adalat_awards WHERE case_type=%s ORDER BY data_year DESC LIMIT 1",
            (case_type,),
        )
        row = cur.fetchone()
        cur.close()
        if not row:
            return None, None, None

        pct  = row["settlement_rate_pct"] / 100.0
        days = row["avg_days_to_settle"]

        if dispute_amount:
            ratio = row["avg_award_amount"] / max(row["avg_claim_amount"], 1)
            amount = int(dispute_amount * ratio)
        else:
            amount = row["avg_award_amount"]

        return amount, pct, days
    except Exception as exc:
        logger.warning("predict_settlement failed: %s", exc)
        return None, None, None
    finally:
        if conn:
            conn.close()


# ── Persistence ───────────────────────────────────────────────────────────────

def store_assessment(case_number: str, case_id: Optional[int], assessment: Dict) -> None:
    conn = None
    try:
        conn = get_mysql_connection()
        cur  = conn.cursor()
        cur.execute(
            """
            INSERT INTO adr_suitability (
                case_id, case_number, case_type, dispute_amount, dispute_years,
                case_complexity, number_of_parties, party_consent_level,
                lok_adalat_score, mediation_score, arbitration_score, negotiation_score,
                recommended_adr, is_lok_adalat_eligible, confidence_level, reasoning,
                predicted_settlement_amount, predicted_settlement_pct, predicted_days_to_settle
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
                lok_adalat_score             = VALUES(lok_adalat_score),
                mediation_score              = VALUES(mediation_score),
                arbitration_score            = VALUES(arbitration_score),
                negotiation_score            = VALUES(negotiation_score),
                recommended_adr              = VALUES(recommended_adr),
                is_lok_adalat_eligible       = VALUES(is_lok_adalat_eligible),
                confidence_level             = VALUES(confidence_level),
                reasoning                    = VALUES(reasoning),
                predicted_settlement_amount  = VALUES(predicted_settlement_amount),
                predicted_settlement_pct     = VALUES(predicted_settlement_pct),
                predicted_days_to_settle     = VALUES(predicted_days_to_settle),
                assessed_at                  = CURRENT_TIMESTAMP
            """,
            (
                case_id,
                case_number,
                assessment.get("case_type"),
                assessment.get("dispute_amount"),
                assessment.get("dispute_years", 0),
                assessment.get("case_complexity", "Moderate"),
                assessment.get("number_of_parties", 2),
                assessment.get("party_consent_level", "Neutral"),
                assessment["lok_adalat_score"],
                assessment["mediation_score"],
                assessment["arbitration_score"],
                assessment["negotiation_score"],
                assessment["recommended_adr"],
                assessment["is_lok_adalat_eligible"],
                assessment["confidence_level"],
                assessment.get("reasoning", ""),
                assessment.get("predicted_settlement_amount"),
                assessment.get("predicted_settlement_pct"),
                assessment.get("predicted_days_to_settle"),
            ),
        )
        conn.commit()
        cur.close()
    except Exception as exc:
        logger.error("store_assessment failed for %s: %s", case_number, exc)
    finally:
        if conn:
            conn.close()


def _store_assessment_mongo(case_number: str, assessment: Dict[str, Any]) -> None:
    if not is_mongo_connected():
        return
    db = get_db()
    now = datetime.utcnow()
    db["case_facts"].update_one(
        {"case_number": case_number},
        {
            "$set": {
                "case_number": case_number,
                "adr_assessment": {
                    "score": assessment.get("lok_adalat_score"),
                    "recommendation": assessment.get("recommended_adr"),
                    "recommended_mechanism": assessment.get("recommended_adr"),
                    "confidence": assessment.get("confidence_level"),
                    "factors": assessment.get("factors", []),
                    "assessed_at": now,
                    "model_version": "rule-ml-hybrid-v2",
                    "full": assessment,
                },
                "updated_at": now,
            }
        },
        upsert=True,
    )


# ── Public API ────────────────────────────────────────────────────────────────

def assess_adr(
    case_number: str,
    metadata: Dict[str, Any],
    text: str = "",
    case_id: Optional[int] = None,
    ecourts_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Full ADR assessment pipeline.
    Called from pipeline_worker during 'predicted' stage.

    Args:
        case_number: Unique case identifier.
        metadata:    Stored case_metadata dict from MongoDB raw_judgments.
        text:        Cleaned judgment text (for extraction fallbacks).
        case_id:     MySQL cases.case_id, if available.

    Returns:
        Complete assessment dict ready for API response.
    """
    case_type = classify_case_type(text, metadata.get("case_type"))
    dispute_amount = (
        metadata.get("dispute_amount")
        or extract_dispute_amount(text)
    )

    # Dispute duration in years
    dispute_years = float(metadata.get("dispute_years", 0) or 0)
    if not dispute_years:
        filing_date = metadata.get("filing_date") or metadata.get("registration_date")
        decision_date = metadata.get("decision_date")
        if filing_date:
            try:
                fd = datetime.strptime(str(filing_date)[:10], "%Y-%m-%d")
                dd = datetime.strptime(str(decision_date)[:10], "%Y-%m-%d") if decision_date else datetime.utcnow()
                dispute_years = max(0.0, (dd - fd).days / 365.25)
            except Exception:
                dispute_years = 0.0

    num_parties = int(metadata.get("number_of_parties", 2) or 2)
    complexity = estimate_complexity(text, num_parties)
    consent = metadata.get("party_consent_level", "Neutral") or "Neutral"
    criminal = is_criminal_case(text)

    scores = score_case(case_type, complexity, consent, dispute_amount, dispute_years, num_parties, criminal)
    adj_delta, adj_reason = _adjournment_adjustment(ecourts_data)
    scores["lok_adalat_score"] = _clamp(int(scores["lok_adalat_score"]) + adj_delta)
    scores["mediation_score"] = _clamp(int(scores["mediation_score"]) + max(0, adj_delta // 2))
    factors = [
        {"name": "case_type", "impact": case_type},
        {"name": "complexity", "impact": complexity},
        {"name": "consent", "impact": consent},
        {"name": "adjournment_pattern", "impact": adj_reason, "delta": adj_delta},
    ]

    amt, pct, days = predict_settlement(case_type, dispute_amount, scores["recommended_adr"])
    scores.update({
        "case_type":                case_type,
        "dispute_amount":           dispute_amount,
        "dispute_years":            round(dispute_years, 1),
        "case_complexity":          complexity,
        "number_of_parties":        num_parties,
        "party_consent_level":      consent,
        "predicted_settlement_amount": amt,
        "predicted_settlement_pct":    round(pct, 3) if pct else None,
        "predicted_days_to_settle":    days,
        "case_number":              case_number,
        "factors": factors,
    })

    store_assessment(case_number, case_id, scores)
    _store_assessment_mongo(case_number, scores)
    return scores


def get_assessment(case_number: str) -> Optional[Dict]:
    """Fetch stored ADR assessment for a case."""
    conn = None
    try:
        conn = get_mysql_connection()
        cur  = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT * FROM adr_suitability WHERE case_number=%s", (case_number,)
        )
        row = cur.fetchone()
        cur.close()
        return row
    except Exception as exc:
        logger.error("get_assessment failed for %s: %s", case_number, exc)
        return None
    finally:
        if conn:
            conn.close()


def get_lok_adalat_eligible(limit: int = 20) -> List[Dict]:
    """Return cases eligible for Lok Adalat, highest score first."""
    conn = None
    try:
        conn = get_mysql_connection()
        cur  = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT a.*, c.title, c.petitioner, c.respondent, c.court_name
            FROM adr_suitability a
            LEFT JOIN cases c ON a.case_number = c.case_number
            WHERE a.is_lok_adalat_eligible = TRUE
            ORDER BY a.lok_adalat_score DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()
        cur.close()
        return rows
    except Exception as exc:
        logger.error("get_lok_adalat_eligible failed: %s", exc)
        return []
    finally:
        if conn:
            conn.close()


def get_adr_dashboard() -> Dict:
    """Aggregate ADR stats for the dashboard endpoint."""
    conn = None
    try:
        conn = get_mysql_connection()
        cur  = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT
                COUNT(*) AS total_assessed,
                SUM(is_lok_adalat_eligible) AS lok_adalat_eligible,
                AVG(lok_adalat_score) AS avg_lok_adalat_score,
                AVG(mediation_score) AS avg_mediation_score,
                AVG(arbitration_score) AS avg_arbitration_score,
                AVG(confidence_level) AS avg_confidence,
                SUM(CASE WHEN recommended_adr='lok_adalat' THEN 1 ELSE 0 END) AS recommended_lok_adalat,
                SUM(CASE WHEN recommended_adr='mediation'  THEN 1 ELSE 0 END) AS recommended_mediation,
                SUM(CASE WHEN recommended_adr='arbitration'THEN 1 ELSE 0 END) AS recommended_arbitration,
                SUM(CASE WHEN recommended_adr='court'      THEN 1 ELSE 0 END) AS recommended_court
            FROM adr_suitability
            """
        )
        row = cur.fetchone() or {}
        cur.close()
        return row
    except Exception as exc:
        logger.error("get_adr_dashboard failed: %s", exc)
        return {}
    finally:
        if conn:
            conn.close()
