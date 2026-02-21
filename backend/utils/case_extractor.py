"""
Legal Document Metadata Extractor — Zone-Based Header Analysis
==============================================================

Strict deterministic extraction. No AI. No guessing.
Returns None for any field that cannot be confidently extracted.
Caller must store None as SQL NULL.

Extraction zones (first page only, top 60 lines):
  TOP ZONE    lines  1-10   → court name
  UPPER ZONE  lines  5-25   → case number, case type, filing year
  MIDDLE ZONE lines 20-80   → parties (petitioner / respondent)
  LOWER ZONE  anywhere      → judge names

SQL columns populated:
  case_number, title, court_name, court_level, bench,
  case_type, filing_date, registration_date, decision_date,
  petitioner, respondent, judge_names, advocates,
  disposition, citation, source, pdf_url
"""

import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

CURRENT_YEAR = datetime.now().year

# ─── Case type prefix map ──────────────────────────────────────────────────────
CASE_TYPE_MAP: Dict[str, str] = {
    "OS":      "Civil Suit",
    "CS":      "Civil Suit",
    "CRL":     "Criminal Case",
    "CRLA":    "Criminal Appeal",
    "CRLA":    "Criminal Appeal",
    "CC":      "Criminal Case",
    "WP":      "Writ Petition",
    "WPC":     "Writ Petition (Civil)",
    "CWP":     "Writ Petition",
    "BA":      "Bail Application",
    "MC":      "Maintenance Case",
    "FC":      "Family Court Case",
    "FCOP":    "Family Court Original Petition",
    "EP":      "Execution Petition",
    "AS":      "Appeal Suit",
    "SA":      "Second Appeal",
    "RSA":     "Regular Second Appeal",
    "RFA":     "Regular First Appeal",
    "CMA":     "Civil Miscellaneous Appeal",
    "OP":      "Original Petition",
    "CP":      "Company Petition",
    "LA":      "Land Acquisition Case",
    "RC":      "Rent Control Case",
    "FMAT":    "First Miscellaneous Appeal",
    "MAT":     "Matrimonial Case",
    "SLP":     "Special Leave Petition",
    "CA":      "Civil Appeal",
    "IA":      "Interlocutory Application",
    "TA":      "Transfer Application",
    "MA":      "Miscellaneous Appeal",
}

# Prefix → broad category (for spec validation)
_PREFIX_CATEGORY: Dict[str, str] = {
    "CRL": "Criminal", "CRLA": "Criminal", "CC": "Criminal", "BA": "Criminal",
    "OS":  "Civil",    "CS":   "Civil",    "AS": "Civil",    "SA": "Civil",
    "WP":  "Writ",     "CWP":  "Writ",     "WPC": "Writ",
    "MC":  "Family",   "FC":   "Family",   "FCOP": "Family", "MAT": "Family",
}

# ─── Court keyword → level ────────────────────────────────────────────────────
_COURT_LEVEL_MAP: List[Tuple[str, str]] = [
    ("SUPREME COURT",        "Supreme Court"),
    ("HIGH COURT",           "High Court"),
    ("PRINCIPAL DISTRICT",   "District Court"),
    ("DISTRICT JUDGE",       "District Court"),
    ("DISTRICT COURT",       "District Court"),
    ("SESSIONS COURT",       "Sessions Court"),
    ("SESSIONS JUDGE",       "Sessions Court"),
    ("CHIEF JUDICIAL MAGISTRATE", "Magistrate Court"),
    ("JUDICIAL FIRST CLASS", "Magistrate Court"),
    ("JUDICIAL MAGISTRATE",  "Magistrate Court"),
    ("FAMILY COURT",         "Family Court"),
    ("TRIBUNAL",             "Tribunal"),
    ("CONSUMER",             "Consumer Forum"),
    ("COURT OF",             "District Court"),  # fallback
]

_COURT_LINE_TRIGGERS = [
    "COURT", "TRIBUNAL", "BENCH", "IN THE HIGH", "IN THE SUPREME",
    "BEFORE THE HON", "DISTRICT JUDGE", "HIGH COURT OF",
    "SESSIONS COURT", "FAMILY COURT", "CHIEF JUDICIAL MAGISTRATE",
    "JUDICIAL FIRST CLASS", "PRINCIPAL DISTRICT",
]

_JUDGE_TRIGGERS = [
    "HON'BLE", "JUSTICE", "CORAM:", "CORAM :", "PRESENT:", "PRESENT :",
    "DR.JUSTICE", "MR.JUSTICE", "MS.JUSTICE", "BEFORE THE HON",
]

_SKIP_TITLES = [
    "HON'BLE", "SRI", "SMT", "JUSTICE", "JUDGE", "CORAM:", "PRESENT:",
    "MR.", "MS.", "DR.", "SHRI", "HON.", "THE HON'BLE",
    "CORAM", "PRESENT", "BEFORE",
]

_ADVOCATE_TRIGGERS = [
    "ADVOCATE", "COUNSEL FOR", "LEARNED COUNSEL", "SENIOR COUNSEL",
    "ADV.", "AOR", "AMICUS", "SOLICITOR", "ATTORNEY",
]

# Disposition: accepted values per final spec
_DISPOSITION_WORDS = [
    "PARTLY ALLOWED",      # check compound values FIRST (before single words)
    "PARTLY DISMISSED",
    "DISPOSED OF",
    "ALLOWED",
    "DISMISSED",
    "DISPOSED",
    "QUASHED",
]

# Canonical display form
_DISPOSITION_CANONICAL = {
    "PARTLY ALLOWED":   "Partly Allowed",
    "PARTLY DISMISSED": "Partly Dismissed",
    "DISPOSED OF":      "Disposed",
    "DISPOSED":         "Disposed",
    "ALLOWED":          "Allowed",
    "DISMISSED":        "Dismissed",
    "QUASHED":          "Quashed",
}

# ─── Case number patterns (ordered: most specific first) ─────────────────────
_CASE_NO_PATTERNS = [
    # FCOP / F.C.O.P
    r"\bF\.?C\.?O\.?P\.?\s*(?:No\.?)?\s*(\d{1,6})\s*(?:/|of)\s*((19|20)\d{2})\b",
    # O.S. / C.S.
    r"\b(O\.?S\.?|C\.?S\.?)\s*(?:No\.?)?\s*(\d{1,6})\s*(?:/|of)\s*((19|20)\d{2})\b",
    # Crl.A / CRL.A / CRLA
    r"\b(Crl\.?A\.?|CRL\.?A\.?|CRLA)\s*(?:No\.?)?\s*(\d{1,6})\s*(?:/|of)\s*((19|20)\d{2})\b",
    # W.P. / WP / CWP / WPC
    r"\b(C?W\.?P\.?C?)\s*(?:No\.?)?\s*(\d{1,6})\s*(?:/|of)\s*((19|20)\d{2})\b",
    # CWP-11649-2024  (dash-separated)
    r"\b(CWP|WP|WPC)\s*-\s*(\d{1,6})\s*-\s*((19|20)\d{2})\b",
    # C.C. / CC
    r"\b(C\.?C\.?)\s*(?:No\.?)?\s*(\d{1,6})\s*(?:/|of)\s*((19|20)\d{2})\b",
    # M.C. / MC
    r"\b(M\.?C\.?)\s*(?:No\.?)?\s*(\d{1,6})\s*(?:/|of)\s*((19|20)\d{2})\b",
    # B.A. / BA
    r"\b(B\.?A\.?)\s*(?:No\.?)?\s*(\d{1,6})\s*(?:/|of)\s*((19|20)\d{2})\b",
    # FMAT / MAT / SLP / CMA / RFA / RSA / SA / AS / EP / OP / LA / RC / CA / IA / TA / MA
    r"\b(FMAT|MAT|SLP|CMA|RFA|RSA|SA|AS|EP|OP|O\.P|CP|LA|RC|CA|IA|TA|MA)\s*(?:No\.?)?\s*(\d{1,6})\s*(?:of|/)\s*((19|20)\d{2})\b",
    # Generic: CRL / WP / OS uppercase 2-5 letter prefix
    r"\b([A-Z]{2,5})\s*\.?\s*(?:No\.?|Case)?\s*(\d{1,6})\s*(?:/|of)\s*((19|20)\d{2})\b",
]

# ─── Date patterns ────────────────────────────────────────────────────────────
_DATE_PATTERNS = [
    r"\b(\d{1,2})[./\-](\d{1,2})[./\-]((19|20)\d{2})\b",          # DD/MM/YYYY
    r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[,.\s]+((19|20)\d{2})\b",
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})[,.\s]+((19|20)\d{2})\b",
]

_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


# ═══════════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _header_lines(text: str, n: int = 60) -> List[str]:
    """Return first n lines of text (first page only)."""
    return text.splitlines()[:n]


def _prepare_header(text: str, n: int = 60) -> Tuple[List[str], str]:
    """
    Stage 1 — Prepare the first-page header for parsing.

    Steps:
      1. Take only the first n lines
      2. Remove empty / whitespace-only lines
      3. Remove pure page-number lines (e.g. '1', 'Page 1', '- 1 -')
      4. Normalize whitespace (collapse multiple spaces)
      5. Return both the cleaned line list AND a single uppercase string for pattern matching

    Returns:
        (cleaned_lines: List[str], upper_text: str)
    """
    raw_lines = text.splitlines()[:n]

    _PAGE_NUM_RE = re.compile(
        r"^[-\s]*(Page\s+)?\d{1,3}[-\s]*$", re.IGNORECASE
    )

    cleaned: List[str] = []
    for line in raw_lines:
        stripped = line.strip()
        if not stripped:                        # skip blank lines
            continue
        if _PAGE_NUM_RE.match(stripped):        # skip page number lines
            continue
        # Normalize internal whitespace
        normalized = re.sub(r"[ \t]{2,}", " ", stripped)
        cleaned.append(normalized)

    upper_text = "\n".join(cleaned).upper()
    return cleaned, upper_text


def _validate_year(year_str: str) -> Optional[int]:
    try:
        y = int(year_str)
        if 1950 <= y <= CURRENT_YEAR:
            return y
    except Exception:
        pass
    return None


def _normalize_prefix(raw: str) -> str:
    key = raw.upper().replace(" ", "").replace(".", "")
    for k in CASE_TYPE_MAP:
        clean_k = k.upper().replace(".", "")
        if clean_k == key or key.startswith(clean_k):
            return k
    return raw.upper()


def _is_advocate_context(match_str: str, context: str) -> bool:
    """Return True if the match appears after an advocate/phone reference."""
    idx = context.find(match_str)
    if idx < 0:
        return False
    snippet = context[max(0, idx - 100): idx].lower()
    bad = ["advocate", "counsel", "phone", "mob", "tel", "enrolment", "bar council",
           "registration no", "enrol"]
    return any(w in snippet for w in bad)



# Keywords that invalidate a party name — these are OCR/boilerplate lines
_PARTY_BAD_KEYWORDS = [
    "judgment", "judgement", "dated", "order", "reserved", "heard",
    "present", "application", "petition filed", "in the", "high court",
    "district court", "sessions", "tribunal", "versus", "v/s",
    "through", "represented", "government of", "ministry of",
]


def _clean_party_name(raw: str) -> Optional[str]:
    """
    Validate and clean a candidate party name.

    Accepts ONLY if ALL conditions pass:
      1. Non-empty after stripping
      2. Length between 3 and 80 characters
      3. At least 70% of characters are alphabetic (rejects dates, OCR noise)
      4. Does NOT contain legal boilerplate keywords (dates, order text, etc.)
      5. Does not start or end with a digit-only segment (rejects pure dates)
    """
    if not raw:
        return None

    # Take first line only, strip common punctuation
    name = raw.strip().split("\n")[0].strip(" .:-,|")
    name = re.sub(r"\s{2,}", " ", name)

    # Rule: length
    if len(name) < 3 or len(name) > 80:
        return None

    # Rule: ≥70% alphabetic characters (reject "02.02.2012", "145/2021", etc.)
    alpha_count = sum(1 for c in name if c.isalpha())
    if alpha_count / max(len(name), 1) < 0.70:
        return None

    # Rule: boilerplate keyword rejection
    name_lower = name.lower()
    for kw in _PARTY_BAD_KEYWORDS:
        if kw in name_lower:
            return None

    # Rule: must not be only a court name
    if "court" in name_lower:
        return None

    # Rule: must contain at least one word of ≥2 letters (not just initials)
    if not re.search(r"[A-Za-z]{2,}", name):
        return None

    return name


def _parse_date(text: str) -> Optional[str]:
    """Try to parse a date string into YYYY-MM-DD. Returns None on failure."""
    # DD/MM/YYYY or DD-MM-YYYY
    m = re.search(r"\b(\d{1,2})[./\-](\d{1,2})[./\-]((19|20)\d{2})\b", text)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}"
    # DD Mon YYYY
    m = re.search(
        r"\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[,.\s]+((19|20)\d{2})\b",
        text, re.IGNORECASE
    )
    if m:
        d = int(m.group(1))
        mo = _MONTH_MAP.get(m.group(2).lower())
        y = int(m.group(3))
        if mo and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}"
    # Month DD, YYYY
    m = re.search(
        r"\b(january|february|march|april|may|june|july|august|september|october|november|december)"
        r"\s+(\d{1,2})[,.\s]+((19|20)\d{2})\b",
        text, re.IGNORECASE
    )
    if m:
        mo = _MONTH_MAP.get(m.group(1).lower())
        d = int(m.group(2))
        y = int(m.group(3))
        if mo and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}"
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# ZONE EXTRACTORS
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_court(lines: List[str]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    TOP ZONE (lines 1–10): Find court name.
    Returns (court_name, court_level, bench).
    Searches strictly first 10 lines as per spec.
    """
    search_zone = lines[:10]   # spec: first 10 lines only
    court_name: Optional[str] = None
    court_level: Optional[str] = None

    for i, line in enumerate(search_zone):
        up = line.strip().upper()
        if not up:
            continue
        if any(trigger in up for trigger in _COURT_LINE_TRIGGERS):
            court_name = line.strip()
            break

    if not court_name:
        return None, None, None

    # Determine level
    up_court = court_name.upper()
    for keyword, level in _COURT_LEVEL_MAP:
        if keyword in up_court:
            court_level = level
            break

    # Bench: look for "Division Bench" / "Single Bench" / "Full Bench" near top 20 lines
    bench: Optional[str] = None
    bench_zone_text = "\n".join(lines[:20])
    bm = re.search(
        r"\b(Division\s+Bench|Single\s+Bench|Full\s+Bench|DB|SB|FB)\b",
        bench_zone_text, re.IGNORECASE
    )
    if bm:
        bench = bm.group(0).strip()

    return court_name, court_level, bench


def _extract_case_number(
    lines: List[str],
    court_line_idx: int,
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[int]]:
    """
    UPPER ZONE (lines 5–25): Extract case number, raw prefix, number, year.
    Returns (formatted_case_number, prefix, case_type, year).
    Skips lines > 120 chars and lines containing PRESENT/CORAM.
    """
    upper_zone = "\n".join(lines[4:26])   # lines 5–26 (0-indexed 4–25)
    upper_lines = lines[4:26]

    candidates = []
    for pat in _CASE_NO_PATTERNS:
        for m in re.finditer(pat, upper_zone, re.IGNORECASE):
            # Find which line this match is on
            line_offset = upper_zone[:m.start()].count("\n")
            src_line = upper_lines[line_offset] if line_offset < len(upper_lines) else ""

            # Reject: line too long
            if len(src_line) > 120:
                continue
            # Reject: PRESENT / CORAM context
            if re.search(r"\bPRESENT\b|\bCORAM\b", src_line, re.IGNORECASE):
                continue
            # Reject: advocate context
            if _is_advocate_context(m.group(0), upper_zone):
                continue

            groups = [g for g in m.groups() if g and re.search(r"(19|20)\d{2}", g) is None]
            year_grp = [g for g in m.groups() if g and re.match(r"(19|20)\d{2}$", g)]

            if not year_grp:
                continue
            year = _validate_year(year_grp[0])
            if year is None:
                continue

            if len(groups) >= 2:
                prefix, number = groups[0], groups[1]
            elif len(groups) == 1:
                prefix, number = "FCOP", groups[0]
            else:
                continue

            norm = _normalize_prefix(prefix)
            case_type = CASE_TYPE_MAP.get(norm) or CASE_TYPE_MAP.get(
                prefix.upper().replace(".", "").replace(" ", ""), None
            )

            # Proximity to court line
            proximity = abs(line_offset - (court_line_idx - 4))
            formatted = m.group(0).strip()
            candidates.append((proximity, formatted, prefix, case_type, year))

    if not candidates:
        return None, None, None, None

    candidates.sort(key=lambda x: x[0])
    _, cn, prefix, case_type, year = candidates[0]

    # Validate: must contain 4-digit year
    if not re.search(r"(19|20)\d{2}", cn):
        return None, None, None, None

    return cn, prefix, case_type, year


def _extract_parties(
    lines: List[str],
) -> Tuple[Optional[str], Optional[str]]:
    """
    MIDDLE ZONE (lines 20–80): Extract petitioner and respondent.
    Priority:
      1. 'A Versus B' or 'A vs B' inline on one line (including V/s)
      2. Petitioner on one line, 'Versus' / 'Vs' / 'V/s' on next, Respondent after
      3. Between / And block
      4. Petitioner / Respondent keyword lines
    """
    zone_text = "\n".join(lines[5:80])
    zone_lines = lines[5:80]
    petitioner: Optional[str] = None
    respondent: Optional[str] = None

    # ── Priority 1: A Versus/V/s/vs B on same line ────────────────────────────
    inline_m = re.search(
        r"([A-Za-z][^\n]{2,100})\s+(?:Versus|Vs\.?|V/[Ss])\s+([A-Za-z][^\n]{2,100})",
        zone_text, re.IGNORECASE
    )
    if inline_m:
        p = _clean_party_name(inline_m.group(1))
        r = _clean_party_name(inline_m.group(2))
        if p and r:
            return p, r

    # ── Priority 2: A \n Versus \n B (across lines) ───────────────────────────
    for i, line in enumerate(zone_lines):
        up = line.strip().upper()
        if re.match(r"^(VERSUS|VS\.?|V/S)$", up):
            # petitioner = line before, respondent = line after
            if i > 0:
                petitioner = _clean_party_name(zone_lines[i - 1])
            if i + 1 < len(zone_lines):
                respondent = _clean_party_name(zone_lines[i + 1])
            if petitioner and respondent:
                return petitioner, respondent

    # ── Priority 3: A\n\nVs.\n\nB (multiline regex) ───────────────────────────
    vs_m = re.search(
        r"^([^\n]{3,120})\s*\n\s*(?:Vs?\.?|Versus|V/[Ss])\s*\n\s*([^\n]{3,120})$",
        zone_text, re.IGNORECASE | re.MULTILINE
    )
    if vs_m:
        p = _clean_party_name(vs_m.group(1))
        r = _clean_party_name(vs_m.group(2))
        if p and r:
            return p, r

    # ── Priority 4: Between / And block ──────────────────────────────────────
    btw_m = re.search(
        r"Between[:\s]+(.+?)\s+And[:\s]+(.+?)(?:\n\n|\Z)",
        zone_text, re.IGNORECASE | re.DOTALL
    )
    if btw_m:
        petitioner = _clean_party_name(btw_m.group(1))
        respondent = _clean_party_name(btw_m.group(2))
        if petitioner and respondent:
            return petitioner, respondent

    # ── Priority 5: Keyword lines ──────────────────────────────────────────────
    for line in zone_lines:
        up = line.strip().upper()
        if re.match(r"^(PETITIONER|PLAINTIFF|COMPLAINANT|APPELLANT)\s*[:\-]", up):
            raw = re.sub(r"^(PETITIONER|PLAINTIFF|COMPLAINANT|APPELLANT)\s*[:\-]\s*", "", line.strip(), flags=re.IGNORECASE)
            petitioner = _clean_party_name(raw)
        elif re.match(r"^(RESPONDENT|DEFENDANT|OPPOSITE PARTY|ACCUSED)\s*[:\-]", up):
            raw = re.sub(r"^(RESPONDENT|DEFENDANT|OPPOSITE PARTY|ACCUSED)\s*[:\-]\s*", "", line.strip(), flags=re.IGNORECASE)
            respondent = _clean_party_name(raw)

    return petitioner, respondent


def _extract_judges(lines: List[str]) -> Optional[str]:
    """
    LOWER ZONE: Find judge name(s) from JUSTICE / CORAM / PRESENT / HON'BLE lines.
    Returns a comma-joined string of names, or None.
    """
    judge_names: List[str] = []

    for i, line in enumerate(lines[:80]):
        up = line.strip().upper()
        if not any(trigger in up for trigger in _JUDGE_TRIGGERS):
            continue

        # Try extracting from this line
        name = line.strip()
        for title in _SKIP_TITLES:
            name = re.sub(re.escape(title), "", name, flags=re.IGNORECASE)
        name = name.strip(" :-\t,.")
        name = re.sub(r"\s{2,}", " ", name)

        # If name is too short, try next line
        if len(name) < 4 and i + 1 < len(lines):
            name = lines[i + 1].strip()

        # Must not contain court keywords
        if len(name) >= 4 and "court" not in name.lower() and len(name) <= 150:
            if name not in judge_names:
                judge_names.append(name)

    return ", ".join(judge_names) if judge_names else None


def _extract_advocates(text: str) -> Optional[str]:
    """Extract advocate names from full text. Returns comma-joined string or None."""
    advocates: List[str] = []
    for line in text.splitlines()[:100]:
        up = line.strip().upper()
        if any(trigger in up for trigger in [t.upper() for t in _ADVOCATE_TRIGGERS]):
            # Extract the name part after the keyword
            name = re.sub(
                r"(Advocate for |Counsel for |Sr\.? Counsel |Senior Counsel |Adv\.|AOR\s+|learned counsel)\s*",
                "", line.strip(), flags=re.IGNORECASE
            ).strip(" :,-")
            name = re.sub(r"\s{2,}", " ", name)
            if 3 < len(name) <= 120 and name not in advocates:
                advocates.append(name)
    return ", ".join(advocates[:6]) if advocates else None


def _extract_disposition(text: str) -> Optional[str]:
    """
    Extract outcome disposition from the last 1500 chars of text.
    Accepts only the 4 spec-valid values: Allowed, Dismissed, Disposed, Quashed.
    Secondary: Partly Allowed, Partly Dismissed.
    """
    tail = text[-1500:].upper()
    for word in _DISPOSITION_WORDS:
        if word in tail:
            return _DISPOSITION_CANONICAL.get(word, word.title())
    return None


def _extract_citation(text: str) -> Optional[str]:
    """
    Extract a law reporter citation: e.g. (2021) 3 SCC 456,  AIR 2020 SC 123.
    """
    # "(YYYY) Vol Reporter PageNo"
    m = re.search(
        r"\(((19|20)\d{2})\)\s+\d+\s+(SCC|AIR|SCR|MLJ|ALT|ALR|ALJR|HLR|BLR|CLR)\s+\d+",
        text, re.IGNORECASE
    )
    if m:
        return m.group(0).strip()
    # "AIR YYYY SC/HC PageNo"
    m = re.search(
        r"\bAIR\s+(19|20)\d{2}\s+(SC|SCC|HC|AP|Bom|Cal|Del|Ker|Mad)\s+\d+\b",
        text, re.IGNORECASE
    )
    if m:
        return m.group(0).strip()
    return None


def _extract_dates(text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Extract filing_date, registration_date, decision_date.
    Looks for keyword-tagged dates in the first 3000 chars of the document.
    Keywords recognised:
      filing:       Filed, Filing Date, Date of Filing
      registration: Registration Date, Registered on
      decision:     Decided on, Judgment on, Judgment date, Order dated,
                    Pronounced on, Date of pronouncement, Date of decision,
                    Heard on (secondary — only if no judgment date found)
    """
    header = text[:3000]
    filing: Optional[str] = None
    registration: Optional[str] = None
    decision: Optional[str] = None
    heard_on: Optional[str] = None

    for line in header.splitlines():
        up = line.upper()

        # Filing date: labeled only — never infer from year
        if re.search(
            r"FILED ON|FILING DATE|DATE OF FILING|PRESENTED ON|PRESENTATION DATE"
            r"|DATE OF PRESENTATION",
            up
        ):
            d = _parse_date(line)
            if d and not filing:
                filing = d

        # Registration date
        elif re.search(r"REGISTRATION DATE|REGISTERED ON", up):
            d = _parse_date(line)
            if d and not registration:
                registration = d

        # Decision / Judgment date (primary)
        elif re.search(
            r"DECIDED ON|JUDGMENT ON|JUDGMENT DATE|ORDER DATED|DATED:\s*"
            r"|PRONOUNCED ON|DATE OF PRONOUNCEMENT|DATE OF DECISION"
            r"|JUDGEMENT ON|DATE OF JUDGEMENT",
            up
        ):
            d = _parse_date(line)
            if d and not decision:
                decision = d

        # "Heard on" — only use as decision_date fallback if nothing better found
        elif re.search(r"HEARD ON|HEARING DATE|ARGUED ON", up):
            d = _parse_date(line)
            if d and not heard_on:
                heard_on = d

    # Use "Heard on" date only as last resort for decision_date
    if not decision and heard_on:
        decision = heard_on

    return filing, registration, decision


def _extract_title(text: str, case_number: Optional[str]) -> Optional[str]:
    """
    Build a clean title from first non-empty line or petitioner vs respondent.
    Never use the raw first line if it's just the court name.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for line in lines[:10]:
        up = line.upper()
        # Skip lines that are just the court name or boilerplate
        if any(kw in up for kw in ["IN THE", "BEFORE THE", "HIGH COURT", "SUPREME COURT"]):
            continue
        if len(line) > 20:
            return line[:200]
    return case_number  # fallback to case number


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def extract_case_metadata(full_text: str) -> Dict[str, Optional[str]]:
    """
    Stage 1–4 pipeline: deterministic metadata extraction from court document header.

    Stage 1: Prepare header (top 60 lines, cleaned — no blank lines, no page numbers,
             normalised whitespace)
    Stage 2: Extract each field from its designated zone
    Stage 3: Validate and clean each field
    Stage 4: Return structured dict for SQL (caller validates before insert)

    Returns dict matching the `cases` SQL table columns.
    Fields that cannot be confidently extracted → None (stored as SQL NULL).
    """
    # ── STAGE 1: Prepare header text ──────────────────────────────────────────
    # Cleaned lines + uppercase string for pattern matching
    lines, _upper = _prepare_header(full_text, n=80)

    # ── STAGE 2: Extract fields from zones ────────────────────────────────────

    # STEP 1: Court (TOP ZONE — first 10 lines after cleaning)
    court_name, court_level, bench = _extract_court(lines)

    # Find the court line index for proximity scoring in case number extraction
    court_line_idx = 0
    for i, line in enumerate(lines[:15]):
        if any(t in line.upper() for t in _COURT_LINE_TRIGGERS):
            court_line_idx = i
            break

    # STEP 2: Case number (UPPER ZONE — lines 5–25)
    case_number, prefix, case_type, case_year = _extract_case_number(lines, court_line_idx)

    # STEP 3: Case type — determined solely from prefix in CASE_TYPE_MAP (no AI)

    # STEP 4: Parties (MIDDLE ZONE — lines 5–80)
    petitioner, respondent = _extract_parties(lines)

    # STEP 5: Judge names
    judge_names = _extract_judges(lines)

    # ── Bonus fields ──────────────────────────────────────────────────────────
    advocates  = _extract_advocates(full_text)
    disposition = _extract_disposition(full_text)
    citation    = _extract_citation(full_text)
    filing_date, registration_date, decision_date = _extract_dates(full_text)

    # ── STEP 6: Validation ────────────────────────────────────────────────────
    # case_number must contain a 4-digit year
    if case_number and not re.search(r"(19|20)\d{2}", case_number):
        case_number = None
        case_type = None
        case_year = None

    # court_level must exist (don't store if absent)
    if not court_level:
        court_level = None

    # petitioner / respondent must not contain "court"
    if petitioner and "court" in petitioner.lower():
        petitioner = None
    if respondent and "court" in respondent.lower():
        respondent = None

    # ── Build title ───────────────────────────────────────────────────────────
    if petitioner and respondent:
        title = f"{petitioner} vs {respondent}"
    else:
        title = _extract_title(full_text, case_number)

    return {
        # Core identification
        "case_number":       case_number,
        "title":             title,
        # Court info
        "court_name":        court_name,
        "court_level":       court_level,
        "bench":             bench,
        # Case classification
        "case_type":         case_type,
        "case_year":         str(case_year) if case_year else None,
        # Dates
        "filing_date":       filing_date,
        "registration_date": registration_date,
        "decision_date":     decision_date,
        # Parties
        "petitioner":        petitioner,
        "respondent":        respondent,
        # People
        "judge_names":       judge_names,
        "advocates":         advocates,
        # Outcome / reference
        "disposition":       disposition,
        "citation":          citation,
        # Source (set by caller)
        "source":            None,
        "pdf_url":           None,
    }


def validate_metadata_for_sql(meta: Dict) -> Tuple[bool, Optional[str]]:
    """
    Validate extracted metadata before inserting into the `cases` SQL table.

    Mandatory fields per final spec:
      1. case_number  — must contain (19xx|20xx) year, must NOT be internal CASE-... ID
      2. court_level  — must not be null/empty
      3. petitioner   — must be a valid party name (not null)
      4. respondent   — must be a valid party name (not null)

    Title is always derived from petitioner+respondent so is never checked separately.
    All other fields (judge_names, advocates, dates, etc.) are optional.

    Returns:
      (True,  None)       — all checks pass, safe to INSERT
      (False, reason_str) — at least one check failed; caller must skip and log
    """
    issues = []

    # Rule 1: case_number — must contain 4-digit year, must not be internal placeholder
    cn = (meta.get("case_number") or "").strip()
    if not cn or cn.upper().startswith("CASE-"):
        issues.append(f"case_number is missing or internal placeholder ('{cn}')")
    elif not re.search(r"(19|20)\d{2}", cn):
        issues.append(f"case_number '{cn}' does not contain a 4-digit year")

    # Rule 2: court_level must exist
    court_level = (meta.get("court_level") or "").strip()
    if not court_level or court_level.lower() in ("none", "unknown"):
        issues.append("court_level is missing (court line must contain COURT/TRIBUNAL/BENCH)")

    # Rule 3: petitioner must be a valid party name
    petitioner = (meta.get("petitioner") or "").strip()
    if not petitioner:
        issues.append("petitioner is missing or could not be extracted")

    # Rule 4: respondent must be a valid party name
    respondent = (meta.get("respondent") or "").strip()
    if not respondent:
        issues.append("respondent is missing or could not be extracted")

    if issues:
        return False, "; ".join(issues)
    return True, None

