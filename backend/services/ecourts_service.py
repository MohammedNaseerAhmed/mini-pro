"""
backend/services/ecourts_service.py

Hybrid eCourts Service Layer with CAPTCHA support.
Follows Option A: Ask user for CAPTCHA in UI.
"""

import asyncio
import logging
import base64
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

from backend.database.mongo import get_db, is_mongo_connected
from backend.database.mysql import get_mysql_connection
from backend.utils.ecourts_parser import parse_ecourts_html

logger = logging.getLogger(__name__)

# Constants
BASE_URL = "https://services.ecourts.gov.in/ecourtindia_v6/"
INDEX_URL = f"{BASE_URL}index.php"
CAPTCHA_URL = f"{BASE_URL}securimage/securimage_show.php"
CNR_POST_URL = f"{BASE_URL}case_status_cnr.php"
REQUEST_TIMEOUT = 30.0

async def get_captcha_for_sync() -> Dict[str, Any]:
    """
    Step 1: Initialize session and fetch CAPTCHA image as base64.
    Returns session cookies and image data.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    
    async with httpx.AsyncClient(headers=headers, timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
        try:
            # Get index to start session
            await client.get(INDEX_URL)
            
            # Fetch captcha image
            captcha_resp = await client.get(CAPTCHA_URL)
            captcha_base64 = base64.b64encode(captcha_resp.content).decode('utf-8')
            
            # Extract cookies to send back to frontend or store
            # For simplicity in this demo, we can just use the client's internal cookie jar
            # but in a stateless API, we might need to return them.
            cookies = client.cookies.get_dict()
            
            return {
                "captcha_image": f"data:image/png;base64,{captcha_base64}",
                "cookies": cookies
            }
        except Exception as exc:
            logger.error("[eCourts] Failed to get CAPTCHA: %s", exc)
            return {"error": str(exc)}

async def sync_with_captcha(case_number: str, cnr: str, captcha_code: str, cookies: Dict[str, str]) -> Dict[str, Any]:
    """
    Step 2: Submit CNR lookup with user-provided CAPTCHA code.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": INDEX_URL
    }
    
    async with httpx.AsyncClient(headers=headers, cookies=cookies, timeout=REQUEST_TIMEOUT) as client:
        try:
            payload = {
                "cino": cnr,
                "captcha_code": captcha_code,
                "ajax_req": "true",
                "court_code": "0",
                "state_code": "0"
            }
            
            resp = await client.post(CNR_POST_URL, data=payload)
            if resp.status_code == 200 and "table" in resp.text:
                return await process_and_store_html(case_number, cnr, resp.text)
            
            if "Invalid Captcha" in resp.text:
                return {"error": "Invalid Captcha code. Please try again."}
                
            logger.warning("[eCourts] Sync failed for %s: %d", cnr, resp.status_code)
            return {"error": "Failed to fetch data from eCourts."}
        except Exception as exc:
            logger.error("[eCourts] Sync exception: %s", exc)
            return {"error": str(exc)}

async def process_and_store_html(case_number: str, cnr: str, html: str, source: str = "scraped") -> Dict[str, Any]:
    """
    Parse eCourts HTML and store results in both MySQL and MongoDB.
    """
    parsed_data = parse_ecourts_html(html)
    parsed_data["case_number"] = case_number
    parsed_data["cnr_number"] = cnr
    parsed_data["source"] = source
    parsed_data["raw_html"] = html
    
    # Save to Mongo
    _save_to_mongo(case_number, cnr, parsed_data)
    
    # Save to MySQL
    _save_to_mysql(parsed_data)
    
    return parsed_data

# ── Database Helpers ─────────────────────────────────────────────────────────

def _save_to_mysql(data: Dict[str, Any]) -> None:
    conn = None
    try:
        conn = get_mysql_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO ecourts_case_status
                (case_number, cnr_number, court_complex, next_hearing_date, 
                 case_stage, judge_assigned, petitioner_name, respondent_name, 
                 raw_html, source, last_synced_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
            ON DUPLICATE KEY UPDATE
                cnr_number        = VALUES(cnr_number),
                next_hearing_date = VALUES(next_hearing_date),
                case_stage        = VALUES(case_stage),
                judge_assigned    = VALUES(judge_assigned),
                raw_html          = VALUES(raw_html),
                source            = VALUES(source),
                last_synced_at    = CURRENT_TIMESTAMP
            """,
            (
                data["case_number"], data["cnr_number"], data.get("court_complex"),
                data.get("next_hearing_date"), data.get("case_stage"),
                data.get("judge_assigned"), data.get("petitioner_name"),
                data.get("respondent_name"), data.get("raw_html"),
                data.get("source")
            )
        )
        conn.commit()
    except Exception as exc:
        logger.error("[eCourts] MySQL write failed: %s", exc)
    finally:
        if conn: conn.close()

def _save_to_mongo(case_number: str, cnr: str, payload: Dict[str, Any]) -> None:
    if not is_mongo_connected(): return
    db = get_db()
    db["ecourts_status"].insert_one({
        "case_number": case_number,
        "cnr": cnr,
        "fetched_at": datetime.utcnow(),
        "payload": payload
    })

def get_stored_status(case_number: str) -> Optional[Dict]:
    conn = None
    try:
        # Normalize the lookup key — strip whitespace, uppercase
        normalized = case_number.strip().upper() if case_number else ""
        if not normalized:
            return None
        conn = get_mysql_connection()
        cur = conn.cursor(dictionary=True)
        # Try direct match first, then try as CNR number
        cur.execute(
            "SELECT * FROM ecourts_case_status WHERE case_number=%s OR cnr_number=%s LIMIT 1",
            (normalized, normalized),
        )
        return cur.fetchone()
    except Exception as exc:
        logger.error("[eCourts] Cache read failed: %s", exc)
        return None
    finally:
        if conn: conn.close()

