"""
backend/services/ecourts_scraper.py

Production-grade eCourts Live Scraping Engine.

Architecture:
  1. Check MySQL cache first (return if fresh < 24h)
  2. Initialize requests.Session with browser-like headers
  3. Load eCourts homepage to capture cookies
  4. POST CNR + CAPTCHA to case_status_cnr.php
  5. Detect CAPTCHA errors / blocked responses
  6. Parse case HTML with BeautifulSoup
  7. Persist to MySQL cache
  8. Return structured JSON

Never crashes FastAPI. Never exposes tracebacks.
"""

import base64
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from backend.database.mysql import get_mysql_connection

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

BASE_URL       = "https://services.ecourts.gov.in/ecourtindia_v6/"
INDEX_URL      = BASE_URL
CAPTCHA_URL    = BASE_URL + "securimage/securimage_show.php"
CNR_POST_URL   = BASE_URL + "case_status_cnr.php"
CACHE_MAX_AGE  = timedelta(hours=24)   # Return cached data if < 24h old
REQUEST_TIMEOUT = 25                   # seconds

# Browser-like headers — eCourts blocks non-browser user agents
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language":  "en-IN,en;q=0.9",
    "Accept-Encoding":  "gzip, deflate, br",
    "Cache-Control":    "no-cache",
    "Pragma":           "no-cache",
    "Upgrade-Insecure-Requests": "1",
    "Connection":       "keep-alive",
}


# ── Step 1: Cache Check ───────────────────────────────────────────────────────

def get_cached_case(cnr_number: str) -> Optional[Dict[str, Any]]:
    """
    Check MySQL cache for a recent result for this CNR / case number.
    Returns the row dict if fresh, else None.
    """
    conn = None
    try:
        normalized = cnr_number.strip().upper()
        conn = get_mysql_connection()
        cur  = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT * FROM ecourts_case_status
            WHERE cnr_number = %s OR case_number = %s
            ORDER BY last_synced_at DESC
            LIMIT 1
            """,
            (normalized, normalized),
        )
        row = cur.fetchone()
        if not row:
            return None

        # Check freshness
        synced_at = row.get("last_synced_at")
        if synced_at:
            if isinstance(synced_at, datetime):
                age = datetime.utcnow() - synced_at
            else:
                age = datetime.utcnow() - datetime.fromisoformat(str(synced_at))
            if age < CACHE_MAX_AGE:
                logger.info("[Scraper] Cache hit for %s (age: %s)", normalized, age)
                row["_source"] = "cache"
                return row

        return None
    except Exception as exc:
        logger.warning("[Scraper] Cache check failed: %s", exc)
        return None
    finally:
        if conn:
            try: conn.close()
            except Exception: pass


# ── Step 2: Session Initialization ───────────────────────────────────────────

def init_ecourts_session() -> Dict[str, Any]:
    """
    Initialize a requests.Session(), visit the eCourts homepage to capture
    session cookies, then fetch the CAPTCHA image as base64.

    Returns:
        {
            "captcha_image": "data:image/png;base64,...",
            "cookies": { ... },
            "success": True
        }
        OR
        { "success": False, "error": "..." }
    """
    session = requests.Session()
    session.headers.update(BROWSER_HEADERS)

    try:
        # Step A: Hit the homepage to get PHPSESSID and other cookies
        logger.info("[Scraper] Initializing session — loading homepage...")
        home_resp = session.get(INDEX_URL, timeout=REQUEST_TIMEOUT)
        home_resp.raise_for_status()
        time.sleep(0.5)   # Brief pause — be a polite browser

        # Step B: Fetch CAPTCHA image
        logger.info("[Scraper] Fetching CAPTCHA image...")
        captcha_resp = session.get(
            CAPTCHA_URL,
            headers={
                **BROWSER_HEADERS,
                "Referer": INDEX_URL,
            },
            timeout=REQUEST_TIMEOUT,
        )
        captcha_resp.raise_for_status()

        # Encode as base64 PNG for frontend
        captcha_b64 = base64.b64encode(captcha_resp.content).decode("utf-8")

        # Capture cookies
        cookies_dict = dict(session.cookies)
        logger.info("[Scraper] Session ready. Cookies: %s", list(cookies_dict.keys()))

        return {
            "success": True,
            "captcha_image": f"data:image/png;base64,{captcha_b64}",
            "cookies": cookies_dict,
        }

    except requests.exceptions.Timeout:
        logger.error("[Scraper] Timeout connecting to eCourts portal.")
        return {"success": False, "error": "eCourts portal timed out. Please try again."}
    except requests.exceptions.ConnectionError:
        logger.error("[Scraper] Connection error reaching eCourts portal.")
        return {"success": False, "error": "Cannot reach eCourts portal. Check your internet connection."}
    except Exception as exc:
        logger.error("[Scraper] Session init failed: %s", exc)
        return {"success": False, "error": f"Failed to initialize eCourts session: {exc}"}


# ── Step 3: Live CNR Search ───────────────────────────────────────────────────

def live_cnr_search(
    cnr_number: str,
    captcha_code: str,
    cookies: Dict[str, str],
) -> Dict[str, Any]:
    """
    Submit CNR + CAPTCHA to eCourts, parse result HTML, persist to MySQL cache.

    Args:
        cnr_number:   The 16-char CNR number (e.g. "MHPN010101234562021")
        captcha_code: The CAPTCHA text entered by the user
        cookies:      Session cookies from init_ecourts_session()

    Returns structured JSON or {"success": False, "error": "..."}
    """
    cnr_clean = cnr_number.strip().upper()

    # ── Guard ─────────────────────────────────────────────────────────────────
    if not cnr_clean:
        return {"success": False, "error": "CNR number cannot be empty."}
    if not captcha_code or not captcha_code.strip():
        return {"success": False, "error": "CAPTCHA code cannot be empty."}

    # ── Cache check ───────────────────────────────────────────────────────────
    cached = get_cached_case(cnr_clean)
    if cached:
        return _format_result(cached, source="cache")

    # ── Initialize session ────────────────────────────────────────────────────
    session = requests.Session()
    session.headers.update(BROWSER_HEADERS)

    # Restore cookies from init step
    for key, val in cookies.items():
        session.cookies.set(key, val)

    try:
        # ── POST to eCourts ───────────────────────────────────────────────────
        payload = {
            "cino":          cnr_clean,
            "captcha_code":  captcha_code.strip(),
            "ajax_req":      "true",
            "court_code":    "0",
            "state_code":    "0",
            "app_token":     "",
        }

        logger.info("[Scraper] Submitting CNR %s to eCourts...", cnr_clean)
        resp = session.post(
            CNR_POST_URL,
            data=payload,
            headers={
                **BROWSER_HEADERS,
                "Referer":      INDEX_URL,
                "Origin":       "https://services.ecourts.gov.in",
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        resp_text = resp.text
        status    = resp.status_code

        logger.info("[Scraper] eCourts responded: HTTP %d, body_len=%d", status, len(resp_text))

        # ── Detect errors in response ─────────────────────────────────────────
        error = _detect_error(resp_text, status)
        if error:
            logger.warning("[Scraper] Error detected: %s", error)
            return {"success": False, "error": error}

        # ── Parse HTML ────────────────────────────────────────────────────────
        parsed = _parse_case_html(resp_text, cnr_clean)

        # ── Persist to MySQL ──────────────────────────────────────────────────
        _persist_to_mysql(cnr_clean, parsed)

        return _format_result(parsed, source="live")

    except requests.exceptions.Timeout:
        return {"success": False, "error": "eCourts portal timed out during search. Please try again."}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "Lost connection to eCourts portal."}
    except Exception as exc:
        logger.error("[Scraper] Live search failed: %s", exc, exc_info=True)
        return {"success": False, "error": "Scraping failed. Please retry."}


# ── HTML Parser ───────────────────────────────────────────────────────────────

def _detect_error(html: str, http_status: int) -> Optional[str]:
    """Scan response for known eCourts error patterns."""
    if http_status == 403:
        return "eCourts portal blocked the request (403 Forbidden). Your IP may be rate-limited."
    if http_status == 503:
        return "eCourts portal is temporarily unavailable (503). Please try again in a few minutes."
    if http_status >= 500:
        return f"eCourts server error (HTTP {http_status}). Please try again."

    lower = html.lower()

    if "invalid captcha" in lower or "captcha code" in lower and "invalid" in lower:
        return "Invalid CAPTCHA code. Please get a fresh CAPTCHA and try again."
    if "session expired" in lower or "session has expired" in lower:
        return "eCourts session expired. Please reload the CAPTCHA and try again."
    if "record not found" in lower or "no record" in lower:
        return "Case not found on eCourts. Please verify the CNR number."
    if "access denied" in lower or "blocked" in lower:
        return "Access denied by eCourts portal. Please wait a few minutes and retry."

    # If none of the expected HTML markers are present
    if "<table" not in lower and "case_no" not in lower and "case no" not in lower:
        # Response may be an error page or blank
        if len(html.strip()) < 200:
            return "eCourts returned an unexpected empty response. Please try again."

    return None   # No error detected


def _parse_case_html(html: str, cnr: str) -> Dict[str, Any]:
    """
    Parse the eCourts case status HTML page into structured data.
    Handles both the modern eCourts v6 layout and legacy table-based layouts.
    """
    soup = BeautifulSoup(html, "html.parser")
    result: Dict[str, Any] = {
        "cnr_number":      cnr,
        "case_number":     cnr,  # Override if found in HTML
        "petitioner_name": "",
        "respondent_name": "",
        "court_complex":   "",
        "judge_assigned":  "",
        "case_stage":      "",
        "next_hearing_date": None,
        "filing_date":     None,
        "acts_sections":   [],
        "orders":          [],
        "hearing_history": [],
        "raw_html":        html[:50_000],  # Store up to 50KB
        "parsed_at":       datetime.utcnow().isoformat(),
    }

    # ── 1. Main case info table (table#charan1 or similar) ────────────────────
    for table in soup.find_all("table"):
        text = table.get_text()
        if any(k in text for k in ("Case No", "CNR No", "Petitioner", "Respondent", "Status")):
            for tr in table.find_all("tr"):
                tds = tr.find_all(["td", "th"])
                if len(tds) < 2:
                    continue
                label = tds[0].get_text(strip=True).lower().rstrip(":").strip()
                value = tds[1].get_text(" ", strip=True).strip()
                _map_label(label, value, result)
            break

    # ── 2. Span-based extractions ─────────────────────────────────────────────
    _try_span(soup, "next_date",    result, "next_hearing_date")
    _try_span(soup, "disp_name",   result, "case_stage")
    _try_span(soup, "case_no_txt", result, "case_number")

    # ── 3. Hearing history ────────────────────────────────────────────────────
    history = _extract_hearing_history(soup)
    if history:
        result["hearing_history"] = history

    # ── 4. Acts and sections ──────────────────────────────────────────────────
    acts = _extract_acts_sections(soup)
    if acts:
        result["acts_sections"] = acts

    # ── 5. Orders ─────────────────────────────────────────────────────────────
    orders = _extract_orders(soup)
    if orders:
        result["orders"] = orders

    # ── 6. Petitioner / Respondent heuristic fallbacks ────────────────────────
    if not result["petitioner_name"]:
        result["petitioner_name"] = _find_party(soup, "Petitioner") or ""
    if not result["respondent_name"]:
        result["respondent_name"] = _find_party(soup, "Respondent") or ""

    # ── 7. Date normalization ─────────────────────────────────────────────────
    result["next_hearing_date"] = _normalise_date(result.get("next_hearing_date"))
    result["filing_date"]       = _normalise_date(result.get("filing_date"))

    return result


def _map_label(label: str, value: str, result: dict) -> None:
    """Map a key→value pair from the HTML table into the result dict."""
    if not value:
        return
    mapping = {
        "cnr number": "cnr_number",
        "case no":    "case_number",
        "case number":"case_number",
        "petitioner": "petitioner_name",
        "respondent": "respondent_name",
        "complainant":"petitioner_name",
        "accused":    "respondent_name",
        "court":      "court_complex",
        "court complex": "court_complex",
        "court establishment": "court_complex",
        "judge":          "judge_assigned",
        "judicial officer": "judge_assigned",
        "case status":    "case_stage",
        "case stage":     "case_stage",
        "status":         "case_stage",
        "next hearing date": "next_hearing_date",
        "next date":         "next_hearing_date",
        "date of filing":    "filing_date",
        "filing date":       "filing_date",
    }
    for k, field in mapping.items():
        if k in label:
            result[field] = value
            return


def _try_span(soup: BeautifulSoup, span_id: str, result: dict, field: str) -> None:
    el = soup.find("span", id=span_id)
    if el:
        val = el.get_text(" ", strip=True)
        if val:
            result[field] = val


def _find_party(soup: BeautifulSoup, role: str) -> Optional[str]:
    """Fallback: scan for text containing role label near a td."""
    el = soup.find(string=lambda t: t and role in t)
    if el:
        td = el.find_next("td")
        if td:
            return td.get_text(" ", strip=True)[:200]
    return None


def _extract_hearing_history(soup: BeautifulSoup) -> List[Dict]:
    """Extract hearing/cause list history from eCourts HTML."""
    history: List[Dict] = []

    # Try common table IDs first
    for table_id in ("historyheading", "cause_list_table", "business_table"):
        tbl = soup.find("table", id=table_id)
        if tbl:
            rows = tbl.find_all("tr")[1:]  # skip header
            for row in rows:
                cols = [c.get_text(" ", strip=True) for c in row.find_all("td")]
                if len(cols) >= 2:
                    history.append({
                        "date":     cols[0] if cols else "",
                        "purpose":  cols[1] if len(cols) > 1 else "",
                        "business": cols[2] if len(cols) > 2 else "",
                        "judge":    cols[3] if len(cols) > 3 else "",
                    })
            return history[:50]

    # Fallback: scan all tables for date-heavy content
    for table in soup.find_all("table"):
        text = table.get_text()
        if "Business Done" in text or "Purpose" in text:
            rows = table.find_all("tr")[1:]
            for row in rows:
                cols = [c.get_text(" ", strip=True) for c in row.find_all("td")]
                if len(cols) >= 2 and re.search(r"\d{2}[-/]\d{2}[-/]\d{4}", cols[0]):
                    history.append({
                        "date":     cols[0],
                        "purpose":  cols[1] if len(cols) > 1 else "",
                        "business": cols[2] if len(cols) > 2 else "",
                        "judge":    cols[3] if len(cols) > 3 else "",
                    })
            if history:
                return history[:50]

    return history


def _extract_acts_sections(soup: BeautifulSoup) -> List[Dict]:
    """Extract Acts and Sections from eCourts HTML."""
    acts: List[Dict] = []

    for tbl in soup.find_all("table"):
        text = tbl.get_text()
        if "Section" in text and ("IPC" in text or "BNS" in text or "Act" in text):
            rows = tbl.find_all("tr")[1:]
            for row in rows:
                cols = [c.get_text(" ", strip=True) for c in row.find_all("td")]
                if cols:
                    acts.append({
                        "act":     cols[0] if cols else "",
                        "section": cols[1] if len(cols) > 1 else "",
                    })
            break

    # Fallback: regex scan
    if not acts:
        text = soup.get_text()
        for m in re.finditer(
            r'(IPC|BNS|CrPC|BNSS|IEA|BSA|NI Act|NDPS)\s+[Ss]ec(?:tion)?\.?\s*(\d+\w*)',
            text
        ):
            acts.append({"act": m.group(1), "section": m.group(2)})

    return acts[:20]


def _extract_orders(soup: BeautifulSoup) -> List[Dict]:
    """Extract court orders from the HTML."""
    orders: List[Dict] = []

    for tbl in soup.find_all("table"):
        text = tbl.get_text()
        if "Order" in text and "Date" in text:
            rows = tbl.find_all("tr")[1:]
            for row in rows:
                cols = [c.get_text(" ", strip=True) for c in row.find_all("td")]
                if len(cols) >= 2:
                    orders.append({
                        "date":    cols[0],
                        "order":   cols[1] if len(cols) > 1 else "",
                        "details": cols[2] if len(cols) > 2 else "",
                    })
            if orders:
                return orders[:20]

    return orders


def _normalise_date(val: Optional[str]) -> Optional[str]:
    if not val:
        return None
    val = val.strip()
    if not val or val.lower() in ("not", "null", "n/a", "-", "—", ""):
        return None
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(val, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return val   # return as-is if no format matched


# ── Persistence ───────────────────────────────────────────────────────────────

def _persist_to_mysql(cnr: str, data: Dict[str, Any]) -> None:
    """Upsert the scraped result into ecourts_case_status."""
    conn = None
    try:
        conn = get_mysql_connection()
        cur  = conn.cursor()
        cur.execute(
            """
            INSERT INTO ecourts_case_status
                (case_number, cnr_number, court_complex, next_hearing_date,
                 case_stage, judge_assigned, petitioner_name, respondent_name,
                 raw_html, source, last_synced_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'scraped',CURRENT_TIMESTAMP)
            ON DUPLICATE KEY UPDATE
                court_complex    = VALUES(court_complex),
                next_hearing_date= VALUES(next_hearing_date),
                case_stage       = VALUES(case_stage),
                judge_assigned   = VALUES(judge_assigned),
                petitioner_name  = VALUES(petitioner_name),
                respondent_name  = VALUES(respondent_name),
                raw_html         = VALUES(raw_html),
                source           = 'scraped',
                last_synced_at   = CURRENT_TIMESTAMP
            """,
            (
                data.get("case_number") or cnr,
                cnr,
                data.get("court_complex")   or "",
                data.get("next_hearing_date"),
                data.get("case_stage")      or "",
                data.get("judge_assigned")  or "",
                data.get("petitioner_name") or "",
                data.get("respondent_name") or "",
                data.get("raw_html", "")[:65_535],  # TEXT limit
            ),
        )
        conn.commit()
        logger.info("[Scraper] Persisted result for CNR %s", cnr)
    except Exception as exc:
        logger.error("[Scraper] MySQL persist failed: %s", exc)
    finally:
        if conn:
            try: conn.close()
            except Exception: pass


# ── Response Formatter ────────────────────────────────────────────────────────

def _format_result(data: Dict[str, Any], source: str = "live") -> Dict[str, Any]:
    """Convert raw scraped/cached dict into the standardized API response."""
    # Handle datetime objects from MySQL
    def _str(v):
        if isinstance(v, datetime):
            return v.isoformat()
        return v

    return {
        "success":         True,
        "source":          source,
        "cnr_number":      _str(data.get("cnr_number") or ""),
        "case_number":     _str(data.get("case_number") or ""),
        "petitioner_name": _str(data.get("petitioner_name") or ""),
        "respondent_name": _str(data.get("respondent_name") or ""),
        "court_complex":   _str(data.get("court_complex") or ""),
        "judge_assigned":  _str(data.get("judge_assigned") or ""),
        "case_stage":      _str(data.get("case_stage") or ""),
        "next_hearing_date": _str(data.get("next_hearing_date")),
        "filing_date":     _str(data.get("filing_date")),
        "acts_sections":   data.get("acts_sections") or [],
        "orders":          data.get("orders") or [],
        "hearing_history": data.get("hearing_history") or [],
        "last_synced_at":  _str(data.get("last_synced_at") or data.get("parsed_at") or ""),
    }
