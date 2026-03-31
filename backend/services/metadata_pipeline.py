import json
import re
from typing import Dict, Optional

from backend.ai.groq_extractor import extract_with_groq
from backend.ai.ollama_extractor import extract_with_ollama
from backend.database.mysql import get_mysql_connection
from backend.services.learning_engine import apply_learning
from backend.utils.case_extractor import extract_case_metadata, validate_metadata_for_sql

MIN_METADATA_CONFIDENCE = 0.82
RUN_BOTH_MODELS_FOR_ACCURACY = True

_PARTY_BAD_TERMS = {
    "the", "and", "or", "vs", "versus", "v", "v/s",
    "petitioner", "respondent", "respondents", "private",
    "others", "anr", "ors", "unknown", "none",
}


def _v(value):
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def calculate_confidence(rule_valid: bool, used_ai: bool, learning_applied: bool = False) -> float:
    score = 0.95 if rule_valid else 0.60
    if used_ai:
        score = max(score, 0.85)
    if learning_applied:
        score = min(0.99, score + 0.02)
    return round(score, 2)


def merge_metadata(rule_meta: Dict, ai_meta: Optional[Dict]) -> Dict:
    final_meta = dict(rule_meta)
    if not ai_meta:
        return final_meta

    for key in final_meta.keys():
        if not _v(final_meta.get(key)) and _v(ai_meta.get(key)):
            final_meta[key] = ai_meta.get(key)
    return final_meta


def is_weak(meta: Dict) -> bool:
    return not (
        _v(meta.get("case_number"))
        and _v(meta.get("petitioner"))
        and _v(meta.get("respondent"))
    )


def _is_valid_party_shape(value: Optional[str]) -> bool:
    party = _v(value)
    if not party:
        return False
    party = party.strip()
    if len(party) < 3 or len(party) > 120:
        return False
    if re.search(r"\b(in the|high court|supreme court|order dated|judgment)\b", party, re.IGNORECASE):
        return False
    words = re.findall(r"[A-Za-z]+", party.lower())
    if not words:
        return False
    if all(w in _PARTY_BAD_TERMS for w in words):
        return False
    if len(words) <= 2 and any(w in _PARTY_BAD_TERMS for w in words):
        return False
    return True


def evaluate_metadata_quality(meta: Dict, confidence_score: float) -> Dict[str, object]:
    reasons = []

    if float(confidence_score or 0.0) < MIN_METADATA_CONFIDENCE:
        reasons.append(
            f"confidence_score below threshold ({confidence_score} < {MIN_METADATA_CONFIDENCE})"
        )

    cn = _v(meta.get("case_number")) or ""
    if not cn or cn.upper().startswith("CASE-") or not re.search(r"(19|20)\d{2}", cn):
        reasons.append("case_number is missing or non-canonical")

    petitioner = _v(meta.get("petitioner"))
    respondent = _v(meta.get("respondent"))
    if not _is_valid_party_shape(petitioner):
        reasons.append("petitioner failed party-shape checks")
    if not _is_valid_party_shape(respondent):
        reasons.append("respondent failed party-shape checks")
    if petitioner and respondent and petitioner.strip().lower() == respondent.strip().lower():
        reasons.append("petitioner and respondent are identical")

    return {
        "quality_gate_passed": len(reasons) == 0,
        "quality_gate_reasons": reasons,
    }


def insert_audit_log(audit_payload: Dict) -> None:
    conn = None
    cursor = None
    try:
        conn = get_mysql_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO case_audit_logs (
                case_id,
                raw_text,
                rule_based_json,
                ai_json,
                final_json,
                learning_applied_json,
                is_rule_valid,
                used_ai,
                confidence_score,
                quality_gate_passed,
                quality_gate_reasons,
                sql_write_allowed
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                audit_payload.get("case_id"),
                audit_payload.get("raw_text"),
                json.dumps(audit_payload.get("rule_based_json") or {}),
                json.dumps(audit_payload.get("ai_json") or {}),
                json.dumps(audit_payload.get("final_json") or {}),
                json.dumps(audit_payload.get("learning_applied_json") or []),
                bool(audit_payload.get("is_rule_valid")),
                bool(audit_payload.get("used_ai")),
                float(audit_payload.get("confidence_score", 0.0)),
                bool(audit_payload.get("quality_gate_passed")),
                json.dumps(audit_payload.get("quality_gate_reasons") or []),
                bool(audit_payload.get("sql_write_allowed")),
            ),
        )
        conn.commit()
    except Exception as exc:
        print(f"[audit] insert failed: {exc}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def process_document_metadata(text: str, case_id: str) -> Dict[str, object]:
    rule_meta = extract_case_metadata(text)
    is_rule_valid, validation_reason = validate_metadata_for_sql(rule_meta)

    ollama_meta = None
    groq_meta = None
    used_ai = False
    should_run_ai = (not is_rule_valid or is_weak(rule_meta) or RUN_BOTH_MODELS_FOR_ACCURACY)
    if should_run_ai:
        ollama_meta = extract_with_ollama(text)
        groq_meta = extract_with_groq(text)
        used_ai = bool(ollama_meta or groq_meta)

    merged_meta = merge_metadata(rule_meta, ollama_meta)
    merged_meta = merge_metadata(merged_meta, groq_meta)

    learning_result = apply_learning(merged_meta)
    final_meta = learning_result["metadata"]
    applied_rules = learning_result["applied_rules"]
    final_is_valid, final_validation_reason = validate_metadata_for_sql(final_meta)
    confidence_score = calculate_confidence(
        rule_valid=is_rule_valid,
        used_ai=used_ai,
        learning_applied=bool(applied_rules),
    )
    quality_result = evaluate_metadata_quality(final_meta, confidence_score)
    sql_write_allowed = bool(final_is_valid and quality_result["quality_gate_passed"])

    final_meta["quality_gate_passed"] = quality_result["quality_gate_passed"]
    final_meta["quality_gate_reasons"] = quality_result["quality_gate_reasons"]
    final_meta["sql_write_allowed"] = sql_write_allowed

    audit_case_id = final_meta.get("case_number") or case_id

    audit_payload = {
        "case_id": audit_case_id,
        "raw_text": text,
        "rule_based_json": rule_meta,
        "ai_json": {
            "ollama": ollama_meta,
            "groq": groq_meta,
        },
        "final_json": final_meta,
        "learning_applied_json": applied_rules,
        "is_rule_valid": is_rule_valid,
        "final_is_valid": final_is_valid,
        "final_validation_reason": final_validation_reason,
        "used_ai": used_ai,
        "confidence_score": confidence_score,
        "quality_gate_passed": quality_result["quality_gate_passed"],
        "quality_gate_reasons": quality_result["quality_gate_reasons"],
        "sql_write_allowed": sql_write_allowed,
    }
    insert_audit_log(audit_payload)

    return {
        "rule_meta": rule_meta,
        "ollama_meta": ollama_meta,
        "groq_meta": groq_meta,
        "final_meta": final_meta,
        "is_rule_valid": is_rule_valid,
        "final_is_valid": final_is_valid,
        "final_validation_reason": final_validation_reason,
        "validation_reason": validation_reason,
        "used_ai": used_ai,
        "confidence_score": confidence_score,
        "quality_gate_passed": quality_result["quality_gate_passed"],
        "quality_gate_reasons": quality_result["quality_gate_reasons"],
        "sql_write_allowed": sql_write_allowed,
        "applied_learning_rules": applied_rules,
        "audit_case_id": audit_case_id,
    }
