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

import re
from typing import List, Optional, Tuple

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
    # Default: try metadata first, fall back to RAG
    return "metadata"


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

def _lexical_retrieve(question: str, k: int = 5) -> List[Tuple[str, str]]:
    db = get_db()
    token_re = re.compile(r"[a-zA-Z]{3,}")
    q_tokens = set(token_re.findall(question.lower()))
    if not q_tokens:
        return []
    chunks = list(db["case_chunks"].find({}, {"case_number": 1, "text": 1}).limit(3000))
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
        scored.append((inter / max(1, len(q_tokens | c_tokens)), cn, chunk.get("text", "")))
    return [(cn, txt) for _, cn, txt in sorted(scored, reverse=True)[:k]]


def _vector_retrieve(question: str, k: int = 4) -> List[Tuple[str, str]]:
    db = get_db()
    results = []
    for cn in vector_store.search(question, k=k):
        doc = db["raw_judgments"].find_one({"case_number": cn})
        if not doc:
            continue
        txt = (doc.get("judgment_text", {}).get("clean_text")
               or doc.get("judgment_text", {}).get("raw_text", ""))
        if txt:
            results.append((cn, txt[:1500]))
    return results


def _get_contexts(question: str) -> List[Tuple[str, str]]:
    seen, out = set(), []
    for cn, txt in (_vector_retrieve(question, k=4) + _lexical_retrieve(question, k=5)):
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


def _answer_rag_content(question: str, case_number: Optional[str] = None) -> dict:
    """
    Answer from document chunks ONLY.
    Never prints metadata block automatically.
    If nothing relevant found → "The judgment does not discuss this information."
    """
    contexts = _get_contexts(question)
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

    all_relevant = []
    for cn, chunk_text in contexts:
        for s in _find_relevant_sentences(question, chunk_text):
            all_relevant.append(f"• {s}")

    if all_relevant:
        answer = "Based on the uploaded document:\n" + "\n".join(all_relevant[:6])
    else:
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


def _answer_legal_knowledge(question: str) -> dict:
    """Answer general Indian law question. Never says 'not found in document'."""
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

def _answer_hybrid(question: str, case_number: Optional[str] = None) -> dict:
    """Explain the law, then apply it to the uploaded case."""
    law_result  = _answer_legal_knowledge(question)
    case_result = _answer_rag_content(question, case_number)

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

def generate_answer(question: str, case_number: Optional[str] = None) -> dict:
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

    intent = _classify_intent(question)

    if intent == "metadata":
        return _answer_metadata(question, case_number)
    elif intent == "rag_content":
        return _answer_rag_content(question, case_number)
    elif intent == "legal_knowledge":
        return _answer_legal_knowledge(question)
    elif intent == "hybrid":
        return _answer_hybrid(question, case_number)
    else:
        return _answer_metadata(question, case_number)
