"""
Manual prediction API — accepts structured feature inputs, returns probability.
Uses weighted scoring rules — no ML model needed, fully deterministic.
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/predict", tags=["Manual Prediction"])


# ─── Input schema ──────────────────────────────────────────────────────────────
class PredictionInput(BaseModel):
    case_type: str = "Civil"
    court_level: str = "District Court"
    act: Optional[str] = ""
    section: Optional[str] = ""
    dispute_type: str = "Property Dispute"
    evidence_strength: str = "medium"    # strong / medium / weak
    delay_in_filing: bool = False
    relief_type: str = "Declaration"


# ─── Scoring tables ────────────────────────────────────────────────────────────

_EVIDENCE_SCORE = {
    "strong": 0.88,
    "medium": 0.58,
    "weak":   0.28,
}

_COURT_SCORE = {
    "supreme court":   0.84,
    "high court":      0.74,
    "district court":  0.62,
    "sessions court":  0.60,
    "magistrate court": 0.55,
    "family court":    0.65,
}

_DISPUTE_SCORE = {
    "property dispute":       0.60,
    "cheque bounce":          0.72,
    "domestic violence":      0.65,
    "maintenance":            0.68,
    "criminal":               0.50,
    "bail":                   0.55,
    "service matter":         0.63,
    "land acquisition":       0.58,
    "motor accident":         0.70,
    "consumer dispute":       0.67,
    "divorce":                0.60,
    "custody":                0.62,
    "writ":                   0.64,
    "contempt":               0.55,
    "defamation":             0.52,
    "injunction":             0.60,
    "recovery":               0.65,
    "insolvency":             0.50,
    "contract breach":        0.63,
    "rent":                   0.60,
}

_RELIEF_SCORE = {
    "compensation":   0.70,
    "declaration":    0.62,
    "injunction":     0.65,
    "bail":           0.55,
    "quashing fir":   0.52,
    "divorce":        0.60,
    "custody":        0.62,
    "maintenance":    0.68,
    "recovery":       0.65,
    "possession":     0.60,
    "specific performance": 0.58,
    "mandamus":       0.63,
    "certiorari":     0.61,
}

_CASE_TYPE_MODIFIER = {
    "civil suit":            +0.04,
    "criminal case":         -0.04,
    "criminal appeal":       -0.02,
    "writ petition":         +0.02,
    "maintenance case":      +0.05,
    "bail application":      -0.06,
    "family court case":     +0.03,
    "family court original petition": +0.03,
}

# ─── Weights ───────────────────────────────────────────────────────────────────
W_EVIDENCE  = 0.35
W_DELAY     = 0.15
W_COURT     = 0.10
W_DISPUTE   = 0.20
W_RELIEF    = 0.20


def _lookup(table: dict, key: str, default: float = 0.60) -> float:
    return table.get(key.strip().lower(), default)


@router.post("/manual")
def predict_manual(data: PredictionInput):
    """
    Weighted scoring prediction:
    - evidence_strength (35%)
    - delay_in_filing  (15%)
    - court_level      (10%)
    - dispute_type     (20%)
    - relief_type      (20%)
    + case_type modifier
    """
    ev_score  = _lookup(_EVIDENCE_SCORE, data.evidence_strength, 0.58)
    delay_sc  = 0.30 if data.delay_in_filing else 0.82
    court_sc  = _lookup(_COURT_SCORE, data.court_level, 0.62)
    dispute_sc= _lookup(_DISPUTE_SCORE, data.dispute_type, 0.60)
    relief_sc = _lookup(_RELIEF_SCORE, data.relief_type, 0.62)

    raw = (
        W_EVIDENCE * ev_score
        + W_DELAY   * delay_sc
        + W_COURT   * court_sc
        + W_DISPUTE * dispute_sc
        + W_RELIEF  * relief_sc
    )

    # Apply case-type modifier
    modifier = _CASE_TYPE_MODIFIER.get(data.case_type.strip().lower(), 0.0)
    score = max(0.05, min(0.95, raw + modifier))

    plaintiff_pct = round(score * 100)
    defendant_pct = 100 - plaintiff_pct

    if score >= 0.65:
        outcome = "Likely Favors Plaintiff"
        explanation = (
            f"Based on the inputs provided, the petitioner (person who filed) appears to have a stronger position. "
            f"Strong evidence, timely filing, and the nature of the dispute ({data.dispute_type}) "
            f"tend to favour the petitioner in similar past cases."
        )
    elif score <= 0.40:
        outcome = "Likely Favors Defendant"
        explanation = (
            f"Based on the inputs, the respondent (defending side) appears to have stronger legal standing. "
            f"{'Delay in filing weakens the case. ' if data.delay_in_filing else ''}"
            f"{'Weak evidence is a major disadvantage. ' if data.evidence_strength == 'weak' else ''}"
            f"Past similar cases often go against the petitioner under these conditions."
        )
    else:
        outcome = "Uncertain"
        explanation = (
            "The case could go either way. The outcome would depend significantly on the actual evidence "
            "presented in court and the judge's interpretation of the applicable law."
        )

    factors = []
    factors.append(f"Evidence strength: {data.evidence_strength} → {round(ev_score*100)}% weight score")
    factors.append(f"Delay in filing: {'Yes — weakens case' if data.delay_in_filing else 'No — good standing'}")
    factors.append(f"Court level: {data.court_level} → {round(court_sc*100)}% base score")
    factors.append(f"Dispute type: {data.dispute_type} → {round(dispute_sc*100)}% typical outcome score")
    factors.append(f"Relief sought: {data.relief_type} → {round(relief_sc*100)}% typical success rate")
    if data.act or data.section:
        factors.append(f"Applicable law: {data.act or ''} {('Section ' + data.section) if data.section else ''}")

    return {
        "outcome": outcome,
        "plaintiff_pct": plaintiff_pct,
        "defendant_pct": defendant_pct,
        "confidence": round(score, 3),
        "explanation": explanation,
        "factors": factors,
        "disclaimer": (
            "This is an educational probability estimate based on weighted rules. "
            "It is NOT a legal opinion and does NOT predict actual court outcomes. "
            "Please consult a qualified advocate for proper legal advice."
        ),
    }
