"""
backend/utils/ecourts_parser.py

BeautifulSoup logic to extract granular case data from eCourts HTML snapshots.
Extracts: Metadata, Hearing History, Status, Next Hearing, Parties.
"""

from bs4 import BeautifulSoup
from datetime import datetime
from typing import Any, Dict, List, Optional

def parse_ecourts_html(html: str) -> Dict[str, Any]:
    """
    Parses the full case status HTML returned by eCourts.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    
    # 1. Base Metadata
    metadata = {}
    table_charan1 = soup.select_one("table#charan1")
    if table_charan1:
        for tr in table_charan1.find_all("tr"):
            tds = tr.find_all(["td", "th"])
            if len(tds) >= 2:
                label = tds[0].get_text(strip=True).lower().replace(":", "").replace(" ", "_")
                value = tds[1].get_text(strip=True)
                metadata[label] = value

    # 2. Next Hearing Date
    next_date_span = soup.select_one("span#next_date")
    next_date_raw = next_date_span.get_text(strip=True) if next_date_span else metadata.get("next_hearing_date")
    
    # 3. Status
    status_span = soup.select_one("span#disp_name")
    status = status_span.get_text(strip=True) if status_span else metadata.get("case_status")

    # 4. Petitioner & Respondent (Detailed extraction)
    petitioner = metadata.get("petitioner", "")
    respondent = metadata.get("respondent", "")
    
    # Often eCourts HTML has separate tables for parties
    # We look for common patterns if not found in main table
    if not petitioner:
        p_el = soup.find(string=lambda t: t and "Petitioner" in t)
        if p_el: petitioner = p_el.find_next("td").get_text(strip=True) if p_el.find_next("td") else ""
        
    if not respondent:
        r_el = soup.find(string=lambda t: t and "Respondent" in t)
        if r_el: respondent = r_el.find_next("td").get_text(strip=True) if r_el.find_next("td") else ""

    # 5. Hearing History (The most critical part for ADR)
    history = []
    history_table = soup.select_one("table#historyheading")
    if not history_table:
        for table in soup.find_all("table"):
            if "Business Done" in table.get_text():
                history_table = table
                break
                
    if history_table:
        rows = history_table.find_all("tr")[1:] # Skip header
        for row in rows:
            cols = [c.get_text(" ", strip=True) for c in row.find_all("td")]
            if len(cols) >= 3:
                history.append({
                    "date": cols[0],
                    "purpose": cols[1] if len(cols) > 1 else "Unknown",
                    "business": cols[2] if len(cols) > 2 else "",
                    "judge": cols[3] if len(cols) > 3 else "",
                })

    return {
        "case_stage": status or "Unavailable",
        "next_hearing_date": _format_date(next_date_raw),
        "court_complex": metadata.get("court_complex") or metadata.get("court_establishment") or "Unknown",
        "judge_assigned": metadata.get("judge") or metadata.get("judicial_officer") or "Unknown",
        "petitioner_name": petitioner or "Unknown",
        "respondent_name": respondent or "Unknown",
        "hearing_history": history[:50],
        "parsed_at": datetime.utcnow().isoformat()
    }

def _format_date(val: Optional[str]) -> Optional[str]:
    if not val or "null" in val.lower() or "not" in val.lower():
        return None
    v = val.strip()
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(v, fmt).strftime("%Y-%m-%d")
        except:
            continue
    return v
