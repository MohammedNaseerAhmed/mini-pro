import re
from typing import List, Set

from fastapi import APIRouter

from backend.ai.embeddings import get_embedding
from backend.database.mongo import get_db
from backend.database.mysql import get_mysql_connection

router = APIRouter()


def _extract_keywords(case_doc) -> Set[str]:
    keywords: Set[str] = set()
    for item in case_doc.get("acts_sections", []) or []:
        act = (item.get("act") or "").strip().lower()
        section = (item.get("section") or "").strip().lower()
        if act:
            keywords.add(act)
        if section:
            keywords.add(f"section {section}")

    text = (
        case_doc.get("judgment_text", {}).get("clean_text")
        or case_doc.get("judgment_text", {}).get("raw_text", "")
    ).lower()
    for m in re.finditer(r"\b(?:section|sec\.?)\s*(\d+[a-z\-]*)", text):
        keywords.add(f"section {m.group(1)}")
    for act in ["ipc", "crpc", "constitution", "evidence act", "contract act"]:
        if act in text:
            keywords.add(act)
    return keywords


def _cosine(a, b) -> float:
    if a is None or b is None:
        return 0.0
    import math

    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    dot = sum(float(a[i]) * float(b[i]) for i in range(n))
    na = math.sqrt(sum(float(a[i]) * float(a[i]) for i in range(n)))
    nb = math.sqrt(sum(float(b[i]) * float(b[i]) for i in range(n)))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def find_similar_cases(case_number: str, top_k: int = 5):
    db = get_db()
    source = db["raw_judgments"].find_one({"case_number": case_number})
    if not source:
        return {"error": "case not found"}

    source_text = source.get("judgment_text", {}).get("clean_text") or source.get("judgment_text", {}).get("raw_text", "")
    source_kw = _extract_keywords(source)
    source_emb = get_embedding(source_text[:2500]) if source_text else None
    if not source_kw and source_emb is None:
        return {"case_number": case_number, "keywords": [], "similar_cases": []}

    candidates = db["raw_judgments"].find(
        {"case_number": {"$ne": case_number}},
        {"case_number": 1, "title": 1, "court_name": 1, "acts_sections": 1, "judgment_text.clean_text": 1, "judgment_text.raw_text": 1},
    ).limit(2500)

    scored = []
    for doc in candidates:
        target_cn = doc.get("case_number")
        if not target_cn:
            continue
        target_kw = _extract_keywords(doc)
        inter = source_kw & target_kw
        kw_score = len(inter) / max(1, len(source_kw | target_kw)) if source_kw or target_kw else 0.0

        target_text = doc.get("judgment_text", {}).get("clean_text") or doc.get("judgment_text", {}).get("raw_text", "")
        sem_score = 0.0
        if source_emb is not None and target_text:
            target_emb = get_embedding(target_text[:2500])
            sem_score = _cosine(source_emb, target_emb)

        # Weighted rank: sections/acts keywords dominate, semantic refines ties.
        final_score = 0.65 * kw_score + 0.35 * max(0.0, sem_score)
        if final_score <= 0:
            continue
        scored.append(
            (
                final_score,
                {
                    "case_number": target_cn,
                    "title": doc.get("title", ""),
                    "court": doc.get("court_name", ""),
                    "similarity_score": float(round(final_score, 4)),
                    "matched_keywords": sorted(list(inter))[:12],
                },
            )
        )

    top = [item for _, item in sorted(scored, key=lambda x: x[0], reverse=True)[:top_k]]
    return {"case_number": case_number, "keywords": sorted(list(source_kw))[:25], "similar_cases": top}


@router.get("/search/{case_number:path}")
def search_similar(case_number: str):
    db = get_db()
    mysql = None
    cursor = None
    try:
        result = find_similar_cases(case_number, top_k=5)
        if "error" in result:
            return result
        top = result["similar_cases"]
        result_case_numbers = [x["case_number"] for x in top]

        mysql = get_mysql_connection()
        cursor = mysql.cursor()
        cursor.execute("SELECT case_id FROM cases WHERE case_number=%s", (case_number,))
        row = cursor.fetchone()
        if row:
            source_case_id = row[0]
            cursor.execute("DELETE FROM similar_cases WHERE case_id=%s", (source_case_id,))
            for item in top:
                cn = item["case_number"]
                score = item["similarity_score"]
                cursor.execute("SELECT case_id FROM cases WHERE case_number=%s", (cn,))
                target = cursor.fetchone()
                if not target:
                    continue
                cursor.execute(
                    """
                    INSERT INTO similar_cases (case_id, similar_case_id, similarity_score)
                    VALUES (%s, %s, %s)
                    """,
                    (source_case_id, target[0], float(score)),
                )
            mysql.commit()

        result["similar_case_numbers"] = result_case_numbers
        return result
    finally:
        if cursor:
            cursor.close()
        if mysql:
            mysql.close()
