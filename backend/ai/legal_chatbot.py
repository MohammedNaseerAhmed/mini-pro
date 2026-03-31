"""
Hybrid Legal AI Chatbot — Four-Route Architecture
==================================================

Route A — METADATA
  Questions about case identity: who filed, judge, court, year, outcome
  → Answer from stored case_metadata fields ONLY
  → If field is NULL: "This information is not mentioned in the document."
  → Never use RAG for metadata questions

Route B — RAG CONTENT
  Questions about case substance: facts, summary, evidence, arguments, reasoning
  → Search document chunks ONLY (vector + lexical)
  → If not found: "The judgment does not discuss this information."
  → Never print metadata block automatically

Route C — LEGAL KNOWLEDGE
  General Indian law questions: IPC, bail, FIR, court process, punishment
  → Answer from built-in legal knowledge base
  → Never say "not found in document"

Route D — MIXED
  "Does section 420 apply in this case?"
  → Explain law first (Route C) then apply to case (Route B)

Safety rules:
  - Never guess missing facts
  - Never output raw OCR noise
  - Never show metadata block unless specifically asked (Route A)
  - Translate only explanation text; never translate names/sections/case numbers
"""

import logging
import re
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

from backend.ai.groq_client import groq_generate, groq_is_configured
from backend.ai.ollama_client import ollama_generate, ollama_is_configured
from backend.ai.prompt_builder import _build_general_legal_prompt, build_chat_prompt
from backend.ai.vector_store import vector_store
from backend.database.mongo import get_db


# ═══════════════════════════════════════════════════════════════════════════════
# 1. INTENT CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

# Route A — metadata signals (answered from SQL/case_metadata fields)
_META_SIGNALS = [
    r"\bwho filed\b", r"\bwho is the petitioner\b", r"\bwho is the respondent\b",
    r"\bpetitioner\b", r"\brespondent\b", r"\bplaintiff\b", r"\bdefendant\b",
    r"\bwho filed\b", r"\bfiled by\b", r"\bopposite party\b", r"\bother side\b",
    r"\bjudge\b", r"\bpresiding judge\b", r"\bjustice\b", r"\bwho is the judge\b",
    r"\bwhich court\b", r"\bwhat court\b", r"\bcourt name\b",
    r"\bcourt level\b", r"\btype of court\b",
    r"\bcase number\b", r"\bcase no\b",
    r"\bcase type\b", r"\bwhat kind of case\b", r"\bnature of case\b",
    r"\bfiling year\b", r"\bcase year\b", r"\bwhich year\b", r"\byear of\b",
    r"\boutcome\b", r"\bverdict\b", r"\bdisposition\b", r"\bresult of\b",
    r"\bwhat was decided\b", r"\bwhat is the result\b", r"\bwas it allowed\b",
    r"\bwas it dismissed\b", r"\badvocate\b", r"\bcounsel for\b",
    r"\bcitation\b", r"\bdate of judgment\b", r"\bwhen was.*decided\b",
]

# Route B — content signals (must search RAG chunks)
_CONTENT_SIGNALS = [
    r"\bfacts\b", r"\bfact of\b", r"\bfacts of the case\b",
    r"\bsummary\b", r"\bbrief\b", r"\bgist\b",
    r"\bkey points\b", r"\bhighlights\b",
    r"\bevidence\b", r"\bwitness\b", r"\bexhibit\b",
    r"\barguments\b", r"\bsubmission\b", r"\bcontended\b",
    r"\breasoning\b", r"\bratio\b", r"\bholding\b",
    r"\bwhat happened\b", r"\bwhat did the court say\b",
    r"\bground\b.*\bappeal\b", r"\brelief sought\b",
    r"\binjunction\b", r"\bstay\b", r"\binterim order\b",
    r"\bdoes this case\b", r"\bin this case\b", r"\bthis judgment\b",
    r"\bthis document\b", r"\bthe document\b", r"\bthe order\b",
]

# Route C — general law signals
_LAW_SIGNALS = [
    r"\bwhat is section\b", r"\bexplain section\b",
    r"\bwhat is (ipc|crpc|cpc|ni act|pocso|pmla|rera|fir|ndps)\b",
    r"\bexplain (ipc|crpc|cpc|ni act|pocso|pmla|rera|fir|ndps|bail)\b",
    r"\bwhat is (bail|anticipatory bail|regular bail|parole)\b",
    r"\bwhat is (writ|injunction|stay order|decree)\b",
    r"\bwhat is (fir|first information report)\b",
    r"\bwhat is (cognizable|non.cognizable)\b",
    r"\bwhat is (locus standi|prima facie|ex.parte)\b",
    r"\bwhat is cheque bounce\b", r"\bwhat is dishonour\b",
    r"\bpunishment for\b", r"\bpenalty for\b",
    r"\bdifference between\b",
    r"\bhow does .{0,30} work\b",
    r"\bmeaning of\b", r"\bdefine\b",
    r"\bwhat are the rights\b", r"\bfundamental rights\b",
    r"\bwhat does article\b", r"\bexplain article\b",
]


def _classify_intent(question: str) -> str:
    """
    Classify question into one of four routes.
    Returns: 'metadata', 'rag_content', 'legal_knowledge', 'hybrid'
    """
    q = question.lower()
    is_meta    = any(re.search(sig, q) for sig in _META_SIGNALS)
    is_content = any(re.search(sig, q) for sig in _CONTENT_SIGNALS)
    is_law     = any(re.search(sig, q) for sig in _LAW_SIGNALS)

    if is_law and (is_meta or is_content):
        return "hybrid"
    if is_law:
        return "legal_knowledge"
    if is_meta and not is_content:
        return "metadata"
    if is_content:
        return "rag_content"
    # Default: try RAG content so general questions get document-grounded answers
    return "rag_content"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. METADATA STORE ACCESS
# ═══════════════════════════════════════════════════════════════════════════════

_META_FIELD_MAP = {
    # Petitioner group
    ("who filed", "petitioner", "plaintiff", "filed by", "filer",
     "complainant", "appellant", "applicant"): "petitioner",
    # Respondent group
    ("respondent", "defendant", "other side", "opposite party",
     "accused", "non-applicant"): "respondent",
    # Court
    ("which court", "what court", "court name", "name of court"): "court_name",
    ("court level", "type of court", "what level"):               "court_level",
    # Case identity
    ("case type", "what kind of case", "nature of case"):         "case_type",
    ("case year", "filing year", "which year", "year of"):        "case_year",
    ("case number", "case no", "number of this case"):            "case_number",
    # People
    ("judge", "presiding judge", "justice", "who is the judge", "judge name"): "judge_names",
    ("bench", "bench type"):                                       "bench",
    ("advocate", "counsel", "lawyer"):                             "advocates",
    # Outcome
    ("outcome", "verdict", "result", "disposition", "decided",
     "was it allowed", "was it dismissed"):                        "disposition",
    # Dates
    ("date of judgment", "when was it decided", "judgment date",
     "decision date"):                                             "decision_date",
    ("citation", "cited as"):                                      "citation",
}

_META_LABELS = {
    "petitioner":    "The petitioner (person who filed) is",
    "respondent":    "The respondent (defending party) is",
    "court_name":    "The court is",
    "court_level":   "The court level is",
    "case_type":     "The case type is",
    "case_year":     "The case was filed in",
    "case_number":   "The case number is",
    "judge_names":   "The presiding judge is",
    "bench":         "The bench composition is",
    "advocates":     "The advocates appearing are",
    "disposition":   "The outcome / disposition is",
    "decision_date": "The date of judgment is",
    "citation":      "The citation is",
}


def _get_meta(case_number: Optional[str] = None) -> dict:
    db = get_db()
    if case_number:
        doc = db["raw_judgments"].find_one({"case_number": case_number})
    else:
        doc = db["raw_judgments"].find_one(
            {"case_metadata": {"$exists": True}},
            sort=[("created_at", -1)]
        )
    return (doc or {}).get("case_metadata", {})


def _match_meta_field(question: str) -> Optional[str]:
    q = question.lower()
    for keywords, field in _META_FIELD_MAP.items():
        if any(kw in q for kw in keywords):
            return field
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# 3. JARGON SIMPLIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

_JARGON = {
    r"\bmaintainable\b":   "acceptable by the court",
    r"\blocus standi\b":   "legal right to file this case",
    r"\bdisposed\b":       "case is finished",
    r"\bex-parte\b":       "decided without the other side present",
    r"\bquash\b":          "cancel or set aside",
    r"\badjournment\b":    "postponing to a later date",
    r"\bprima facie\b":    "based on first look",
    r"\bjurisdiction\b":   "legal authority of the court",
    r"\blimitation\b":     "time limit for filing",
    r"\baffidavit\b":      "written sworn statement",
    r"\binjunction\b":     "court order to stop or allow something",
    r"\bstay order\b":     "temporary pause on a decision",
}

def _simplify(text: str) -> str:
    for pat, rep in _JARGON.items():
        text = re.sub(pat, rep, text, flags=re.IGNORECASE)
    return text


def _is_weak_answer(answer: str) -> bool:
    answer_text = (answer or "").strip()
    if len(answer_text) < 40:
        return True
    weak_signals = [
        "not mentioned",
        "not provided",
        "do not know",
        "don't know",
        "cannot determine",
    ]
    lower = answer_text.lower()
    return any(signal in lower for signal in weak_signals)


def _score_answer_quality(answer: str, context: str) -> float:
    """
    Lightweight quality scorer:
    - penalize weak/very short answers
    - reward lexical overlap with context (grounding proxy)
    """
    ans = (answer or "").strip()
    if not ans:
        return 0.0
    if _is_weak_answer(ans):
        return 0.1

    token_re = re.compile(r"[a-zA-Z]{3,}")
    ans_tokens = set(token_re.findall(ans.lower()))
    ctx_tokens = set(token_re.findall((context or "").lower()))
    if not ans_tokens:
        return 0.2

    overlap = len(ans_tokens & ctx_tokens) / max(1, len(ans_tokens))
    length_bonus = min(len(ans) / 500.0, 0.25)
    return round(0.4 + overlap + length_bonus, 3)


def smart_chatbot(question: str, context: str, chat_history: List[dict] = None) -> Optional[str]:
    prompt = build_chat_prompt(question, context, chat_history=chat_history)
    candidates: List[Tuple[float, str, str]] = []

    # Accuracy mode: try both models when available and choose best-scored answer.
    if ollama_is_configured():
        try:
            ollama_answer = (ollama_generate(prompt) or "").strip()
            if ollama_answer:
                candidates.append((_score_answer_quality(ollama_answer, context), ollama_answer, "ollama"))
        except Exception as e:
            logger.warning("[smart_chatbot] Ollama failed: %s", e)

    if groq_is_configured():
        try:
            groq_answer = (groq_generate(prompt) or "").strip()
            if groq_answer:
                candidates.append((_score_answer_quality(groq_answer, context), groq_answer, "groq"))
        except Exception as e:
            logger.warning("[smart_chatbot] Groq failed: %s", e)

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    best_text  = candidates[0][1].strip()
    best_model = candidates[0][2]
    return (best_text, best_model) if best_text else None


# ═══════════════════════════════════════════════════════════════════════════════
# 4. ROUTE A — METADATA ANSWER
# ═══════════════════════════════════════════════════════════════════════════════

def _answer_metadata(question: str, case_number: Optional[str] = None) -> dict:
    """
    Answer strictly from case_metadata field.
    If the field is NULL / missing → polite not-found message.
    Never uses RAG or guesses.
    """
    meta = _get_meta(case_number)
    field = _match_meta_field(question)

    if field and meta:
        value = meta.get(field)
        # Normalize: treat "unknown", "none", "" as NULL
        if value and str(value).strip().lower() not in ("unknown", "none", ""):
            label = _META_LABELS.get(field, f"The {field.replace('_', ' ')} is")
            return {
                "answer": f"{label}: **{value}**",
                "retrieved_case_ids": [meta.get("case_number", "")],
                "mode": "metadata",
            }
        else:
            return {
                "answer": (
                    f"This information ({field.replace('_', ' ')}) is not mentioned "
                    "in the uploaded document."
                ),
                "retrieved_case_ids": [],
                "mode": "metadata",
            }

    # No matching field found — try to be helpful
    if not meta:
        return {
            "answer": "No document has been uploaded yet. Please upload a court document first.",
            "retrieved_case_ids": [],
            "mode": "metadata",
        }

    return {
        "answer": "This information is not mentioned in the uploaded document.",
        "retrieved_case_ids": [],
        "mode": "metadata",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 5. ROUTE B — RAG CONTENT ANSWER
# ═══════════════════════════════════════════════════════════════════════════════

def _lexical_retrieve(question: str, k: int = 5, case_number: Optional[str] = None) -> List[Tuple[str, str]]:
    db = get_db()
    token_re = re.compile(r"[a-zA-Z]{3,}")
    q_tokens = set(token_re.findall(question.lower()))
    if not q_tokens:
        return []
    query = {"case_number": case_number} if case_number else {}
    chunks = list(db["case_chunks"].find(query, {"case_number": 1, "text": 1, "chunk_type": 1}).limit(3000))
    scored = []
    for chunk in chunks:
        txt = (chunk.get("text") or "").lower()
        cn  = chunk.get("case_number")
        if not txt or not cn:
            continue
        c_tokens = set(token_re.findall(txt))
        inter = len(q_tokens & c_tokens)
        if inter == 0:
            continue
        score = inter / max(1, len(q_tokens | c_tokens))
        if chunk.get("chunk_type") == "header":
            score += 0.25
        scored.append((score, cn, chunk.get("text", "")))
    return [(cn, txt) for _, cn, txt in sorted(scored, reverse=True)[:k]]


def _vector_retrieve(question: str, k: int = 4, case_number: Optional[str] = None) -> List[Tuple[str, str]]:
    db = get_db()
    results = []
    candidate_cases = vector_store.search(question, k=k * 2)
    for cn in candidate_cases:
        if case_number and cn != case_number:
            continue
        doc = db["raw_judgments"].find_one({"case_number": cn})
        if not doc:
            continue
        txt = (doc.get("judgment_text", {}).get("clean_text")
               or doc.get("judgment_text", {}).get("raw_text", ""))
        if txt:
            results.append((cn, txt[:1500]))
        if len(results) >= k:
            break
    return results


def _header_retrieve(question: str, k: int = 2, case_number: Optional[str] = None) -> List[Tuple[str, str]]:
    db = get_db()
    token_re = re.compile(r"[a-zA-Z]{3,}")
    q_tokens = set(token_re.findall(question.lower()))
    query = {"chunk_type": "header"}
    if case_number:
        query["case_number"] = case_number

    header_chunks = list(db["case_chunks"].find(query, {"case_number": 1, "text": 1}).limit(200))
    scored = []
    for chunk in header_chunks:
        text = chunk.get("text") or ""
        cn = chunk.get("case_number")
        if not text or not cn:
            continue
        tokens = set(token_re.findall(text.lower()))
        overlap = len(q_tokens & tokens) if q_tokens else 1
        scored.append((overlap, cn, text))

    if scored:
        return [(cn, txt) for _, cn, txt in sorted(scored, reverse=True)[:k]]

    # Backward compatibility for already-processed cases without header chunks.
    fallback_query = {"case_number": case_number} if case_number else {}
    docs = list(
        db["raw_judgments"].find(
            fallback_query,
            {"case_number": 1, "judgment_text.raw_text": 1, "created_at": 1},
        ).sort("created_at", -1).limit(k)
    )
    out = []
    for doc in docs:
        cn = doc.get("case_number")
        raw = (doc.get("judgment_text", {}) or {}).get("raw_text", "")
        header = "\n".join([line.strip() for line in raw.splitlines()[:40] if line.strip()])
        if cn and header:
            out.append((cn, header[:1800]))
    return out[:k]


def _get_contexts(question: str, case_number: Optional[str] = None) -> List[Tuple[str, str]]:
    seen, out = set(), []
    for cn, txt in (
        _header_retrieve(question, k=2, case_number=case_number)
        + _vector_retrieve(question, k=4, case_number=case_number)
        + _lexical_retrieve(question, k=5, case_number=case_number)
    ):
        if cn not in seen:
            seen.add(cn)
            out.append((cn, txt))
    return out[:5]


def _find_relevant_sentences(question: str, text: str, min_overlap: int = 2) -> List[str]:
    token_re = re.compile(r"[a-zA-Z]{3,}")
    stop = {
        "the", "and", "for", "that", "with", "this", "are", "has", "have",
        "was", "were", "what", "when", "how", "did", "does", "can", "will",
        "from", "which", "case", "court",
    }
    q_tokens = set(token_re.findall(question.lower())) - stop
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 15]
    return [
        _simplify(s) for s in sents
        if len(q_tokens & (set(token_re.findall(s.lower())) - stop)) >= min_overlap
    ][:5]


def _answer_rag_content(
    question: str,
    case_number: Optional[str] = None,
    chat_history: List[dict] = None,
) -> dict:
    """
    Answer from document chunks ONLY.
    Never prints metadata block automatically.
    If nothing relevant found → "The judgment does not discuss this information."
    """
    contexts = _get_contexts(question, case_number=case_number)
    case_ids = [cn for cn, _ in contexts]

    if not contexts:
        return {
            "answer": (
                "The judgment does not discuss this information, or no document "
                "has been uploaded yet. Please upload a court document first."
            ),
            "retrieved_case_ids": [],
            "mode": "rag_content",
        }

    llm_context = "\n\n".join([f"[Case {cn}]\n{txt}" for cn, txt in contexts])
    llm_result = smart_chatbot(question, llm_context, chat_history=chat_history)
    llm_answer = None
    if llm_result:
        llm_answer = llm_result[0] if isinstance(llm_result, tuple) else llm_result
    if llm_answer and not _is_weak_answer(llm_answer):
        return {"answer": llm_answer, "retrieved_case_ids": case_ids, "mode": "rag_content"}

    all_relevant = []
    for cn, chunk_text in contexts:
        for s in _find_relevant_sentences(question, chunk_text):
            all_relevant.append(f"• {s}")

    if all_relevant:
        answer = "Based on the uploaded document:\n" + "\n".join(all_relevant[:6])
    else:
        # If RAG is weak and question has legal-knowledge intent, use legal route fallback.
        if _classify_intent(question) in ("legal_knowledge", "hybrid"):
            law_fallback = _answer_legal_knowledge(question, chat_history=chat_history)
            return {
                "answer": law_fallback["answer"],
                "retrieved_case_ids": [],
                "mode": "legal_knowledge",
            }
        answer = "The judgment does not discuss this information."

    return {"answer": answer, "retrieved_case_ids": case_ids, "mode": "rag_content"}


# ═══════════════════════════════════════════════════════════════════════════════
# 6. ROUTE C — LEGAL KNOWLEDGE ANSWER
# ═══════════════════════════════════════════════════════════════════════════════

_LEGAL_KB: List[Tuple[List[str], str]] = [
    (["fir", "first information report"],
     "An **FIR (First Information Report)** is the first complaint registered by police when "
     "someone reports a cognizable offence. It sets the criminal case in motion. You can file "
     "an FIR at any police station. If police refuse, approach a Magistrate under Section 156(3) CrPC."),

    (["ipc", "indian penal code"],
     "The **IPC (Indian Penal Code, 1860)** is India's main criminal code. It defines crimes and "
     "prescribes punishments. Key sections: Section 302 = Murder (up to death penalty), "
     "Section 420 = Cheating (up to 7 years), Section 498A = Cruelty to wife (up to 3 years)."),

    (["crpc", "code of criminal procedure", "criminal procedure"],
     "The **CrPC (Code of Criminal Procedure, 1973)** is the procedural law for criminal cases — "
     "how arrests are made, how trials proceed, how bail is granted, how sentences are carried out."),

    (["cpc", "code of civil procedure", "civil procedure"],
     "The **CPC (Code of Civil Procedure, 1908)** governs civil court proceedings — how civil suits "
     "are filed, how evidence is recorded, and how decrees are enforced."),

    (["138", "ni act", "cheque bounce", "dishonour", "negotiable instruments"],
     "**Section 138 NI Act** — Cheque dishonour (bounce). If a cheque is returned due to "
     "insufficient funds, it is a criminal offence. Punishment: up to 2 years imprisonment OR "
     "twice the cheque amount as fine. The payee must send a legal notice within 30 days of "
     "dishonour and file a case within 30 days of no payment."),

    (["bail", "anticipatory bail", "regular bail", "parole"],
     "**Bail** is temporary release from custody during trial. Types: "
     "**Regular Bail** (after arrest, Section 437/439 CrPC), "
     "**Anticipatory Bail** (before arrest, Section 438 CrPC). "
     "Bail can be denied if the offence is serious or there is risk of flight or evidence tampering."),

    (["writ", "writ petition", "habeas corpus", "mandamus", "certiorari"],
     "A **Writ Petition** enforces fundamental rights or challenges illegal government acts. "
     "Five types: Habeas Corpus (produce the detainee), Mandamus (order a public body to act), "
     "Certiorari (quash a lower court order), Prohibition (stop excess jurisdiction), "
     "Quo Warranto (challenge a public official's authority)."),

    (["pocso", "protection of children"],
     "**POCSO Act, 2012** protects children under 18 from sexual offences. "
     "Minimum punishment: 10 years to life imprisonment. Cases must be "
     "tried in Special Courts and completed within one year."),

    (["locus standi", "legal standing", "right to file"],
     "**Locus standi** = the legal right to file a case. Usually only the directly affected "
     "party can file. In PIL (Public Interest Litigation), any citizen can file on behalf of the public."),

    (["prima facie", "at first look"],
     "**Prima facie** means 'at first look'. When a court says a case is prima facie valid, "
     "there is enough evidence to proceed — but it is not a final decision."),

    (["cognizable", "non cognizable", "non-cognizable"],
     "**Cognizable offence** — police can arrest WITHOUT a warrant (murder, rape, robbery). "
     "FIR is mandatory. "
     "**Non-cognizable offence** — police need court permission to arrest (minor assault, cheating). "
     "A complaint (not FIR) is filed."),

    (["injunction", "stay order", "interim relief"],
     "An **Injunction** is a court order directing someone to do or stop doing something. "
     "A **Stay Order** temporarily halts a proceeding or execution. These are interim reliefs "
     "granted while the main case is pending."),

    (["decree", "order", "difference between decree"],
     "A **Decree** is the final decision in a civil case determining both parties' rights. "
     "An **Order** is an interim decision during the case. "
     "In criminal cases, the final decision is called a **Judgment**."),

    (["fundamental rights", "article 14", "article 19", "article 21", "article 32"],
     "**Fundamental Rights** (Part III, Constitution): "
     "Article 14 — Equality before law, "
     "Article 19 — Freedom of speech, movement, profession, "
     "Article 21 — Right to Life and Personal Liberty (no arrest without due process), "
     "Article 32 — Right to approach Supreme Court to enforce Fundamental Rights."),

    (["civil", "criminal", "difference between civil and criminal"],
     "**Civil case** — dispute between private parties (property, contracts, family). "
     "Result: compensation, decree. "
     "**Criminal case** — State prosecutes a person for breaking law. "
     "Result: conviction, imprisonment, fine. "
     "Example: Cheque bounce is both civil (recovery suit) AND criminal (Section 138 NI Act)."),

    (["pmla", "money laundering"],
     "**PMLA (Prevention of Money Laundering Act, 2002)** targets disguising illegal money as "
     "legitimate income. Investigated by the Enforcement Directorate (ED). Property can be "
     "attached. Bail is very difficult in PMLA cases."),

    (["rera", "real estate regulatory"],
     "**RERA Act, 2016** protects homebuyers. Builders must register projects with RERA. "
     "Penalty for delay or changes: up to 10% of project cost or 3 years jail."),

    (["mact", "motor accident", "motor vehicle", "compensation"],
     "**MACT (Motor Accident Claims Tribunal)** handles compensation claims for road accidents. "
     "Governed by the Motor Vehicles Act. Compensation covers medical expenses, loss of income, "
     "and death compensation to dependants."),

    (["section 420", "section 302", "section 498", "section 376", "section 307"],
     "Common IPC sections: Section 302 = Murder, Section 307 = Attempt to murder, "
     "Section 376 = Rape, Section 420 = Cheating, Section 498A = Cruelty to wife, "
     "Section 324 = Voluntarily causing hurt."),
]


def _answer_legal_question(question: str) -> Optional[str]:
    q_lower = question.lower()
    q_tokens = set(re.findall(r"[a-z]{3,}", q_lower))
    best_score, best_answer = 0, None
    for keywords, explanation in _LEGAL_KB:
        score = sum(1 for kw in keywords if kw in q_lower)
        kw_tokens = set(tok for kw in keywords for tok in kw.split())
        score += len(q_tokens & kw_tokens) * 0.5
        if score > best_score:
            best_score = score
            best_answer = explanation
    return best_answer if best_score >= 1.0 else None


def _answer_general_with_models(question: str, chat_history: List[dict] = None) -> Optional[str]:
    prompt = _build_general_legal_prompt(question, chat_history=chat_history)
    candidates: List[Tuple[float, str]] = []

    if ollama_is_configured():
        try:
            answer = (ollama_generate(prompt) or "").strip()
            if answer:
                candidates.append((_score_answer_quality(answer, prompt), answer))
        except Exception as e:
            logger.warning("[general_with_models] Ollama failed: %s", e)

    if groq_is_configured():
        try:
            answer = (groq_generate(prompt) or "").strip()
            if answer:
                candidates.append((_score_answer_quality(answer, prompt), answer))
        except Exception as e:
            logger.warning("[general_with_models] Groq failed: %s", e)

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]

def _answer_legal_knowledge(question: str, chat_history: List[dict] = None) -> dict:
    """Answer general Indian law question. Never says 'not found in document'."""
    model_answer = _answer_general_with_models(question, chat_history=chat_history)
    if model_answer and not _is_weak_answer(model_answer):
        return {
            "answer": f"⚖️ **Legal Knowledge**\n\n{model_answer}",
            "retrieved_case_ids": [],
            "mode": "legal_knowledge",
        }

    explanation = _answer_legal_question(question)
    if explanation:
        return {
            "answer": f"⚖️ **Legal Knowledge**\n\n{explanation}",
            "retrieved_case_ids": [],
            "mode": "legal_knowledge",
        }
    return {
        "answer": (
            "⚖️ **Legal Knowledge**\n\n"
            "I can explain the following topics: IPC, CrPC, CPC, NI Act (cheque bounce), "
            "bail, anticipatory bail, writ petitions, POCSO, fundamental rights (Articles 14/19/21), "
            "FIR, cognizable vs non-cognizable, civil vs criminal cases, PMLA, RERA, MACT, "
            "injunction, stay order, prima facie, locus standi, common IPC sections.\n\n"
            "Please ask about any of these."
        ),
        "retrieved_case_ids": [],
        "mode": "legal_knowledge",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 7. ROUTE D — HYBRID ANSWER
# ═══════════════════════════════════════════════════════════════════════════════

def _answer_hybrid(
    question: str,
    case_number: Optional[str] = None,
    chat_history: List[dict] = None,
) -> dict:
    """Explain the law, then apply it to the uploaded case."""
    law_result = _answer_legal_knowledge(question, chat_history=chat_history)
    case_result = _answer_rag_content(question, case_number, chat_history=chat_history)

    law_part  = law_result["answer"]
    case_part = case_result["answer"]

    combined = f"{law_part}\n\n---\n\n📁 **Applied to This Case**\n\n{case_part}"
    return {
        "answer": combined,
        "retrieved_case_ids": case_result.get("retrieved_case_ids", []),
        "mode": "hybrid",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 8. PUBLIC ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def generate_answer(
    question: str,
    case_number: Optional[str] = None,
    response_mode: str = "auto",
    chat_history: List[dict] = None,
) -> dict:
    """
    Main chatbot entry point. Routes question to correct handler.

    Args:
        question:    User question string.
        case_number: Optional — scope search to a specific case.

    Returns:
        { "answer": str, "retrieved_case_ids": list, "mode": str }

    Mode values:
        metadata       — answered from case_metadata fields
        rag_content    — answered from document chunks
        legal_knowledge — answered from built-in legal KB
        hybrid         — law explanation + case application
        none           — empty question
    """
    question = (question or "").strip()
    if not question:
        return {
            "answer": (
                "Please ask me a question. I can answer:\n"
                "• **Case info**: who filed, judge, court, year, outcome\n"
                "• **Case content**: facts, summary, evidence, arguments\n"
                "• **Indian law**: bail, FIR, IPC, POCSO, writ, cheque bounce, etc.\n"
                "• **Mixed**: 'Does Section 420 apply in this case?'"
            ),
            "retrieved_case_ids": [],
            "mode": "none",
        }

    mode = (response_mode or "auto").strip().lower()
    if mode in ("hybrid", "hybrid_always", "mixed"):
        return _answer_hybrid(question, case_number, chat_history=chat_history)
    if mode in ("rag", "document", "document_rag"):
        return _answer_rag_content(question, case_number, chat_history=chat_history)
    if mode in ("general", "legal", "legal_knowledge"):
        return _answer_legal_knowledge(question, chat_history=chat_history)
    if mode in ("metadata",):
        return _answer_metadata(question, case_number)

    intent = _classify_intent(question)

    if intent == "metadata":
        return _answer_metadata(question, case_number)
    elif intent == "rag_content":
        return _answer_rag_content(question, case_number, chat_history=chat_history)
    elif intent == "legal_knowledge":
        return _answer_legal_knowledge(question, chat_history=chat_history)
    elif intent == "hybrid":
        return _answer_hybrid(question, case_number, chat_history=chat_history)
    else:
        return _answer_metadata(question, case_number)
