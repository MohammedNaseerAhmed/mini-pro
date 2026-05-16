"""
backend/scripts/seed_section_mappings.py

Seed the section_mappings table with authoritative IPC -> BNS,
CrPC -> BNSS, and IEA -> BSA mappings.

Run once: python -m backend.scripts.seed_section_mappings

Source: Ministry of Home Affairs circulars, Bharatiya Nyaya Sanhita 2023,
        Bharatiya Nagarik Suraksha Sanhita 2023,
        Bharatiya Sakshya Adhiniyam 2023.
Effective date: July 1, 2024.
"""

import json
import logging
import os
from backend.database.mysql import get_mysql_connection

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Path to the JSON data file
JSON_PATH = os.path.join("backend", "data", "section_mappings.json")

def load_mappings():
    """Load mappings from JSON file."""
    if not os.path.exists(JSON_PATH):
        logger.error("JSON mapping file not found at %s", JSON_PATH)
        return []
    with open(JSON_PATH, "r") as f:
        return json.load(f)

def run():
    mappings = load_mappings()
    if not mappings:
        print("No mappings to seed.")
        return

    conn = get_mysql_connection()
    cur  = conn.cursor()
    inserted = 0
    skipped  = 0

    for m in mappings:
        old_act     = m.get("old_act")
        old_sec     = m.get("old_section")
        old_title   = m.get("old_title")
        new_act     = m.get("new_act")
        new_sec     = m.get("new_section")
        new_title   = m.get("new_title")
        change_type = m.get("change_type")
        notes       = m.get("change_notes")
        critical    = m.get("is_critical", False)

        try:
            cur.execute(
                """
                INSERT INTO section_mappings
                    (old_act, old_section, old_title, new_act, new_section, new_title,
                     change_type, change_notes, is_critical)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    old_title    = VALUES(old_title),
                    new_act      = VALUES(new_act),
                    new_section  = VALUES(new_section),
                    new_title    = VALUES(new_title),
                    change_type  = VALUES(change_type),
                    change_notes = VALUES(change_notes),
                    is_critical  = VALUES(is_critical)
                """,
                (old_act, old_sec, old_title, new_act, new_sec, new_title,
                 change_type, notes, bool(critical)),
            )
            if cur.rowcount == 1:
                inserted += 1
            else:
                skipped += 1
        except Exception as exc:
            logger.warning("Failed to insert %s %s: %s", old_act, old_sec, exc)

    conn.commit()
    cur.close()
    conn.close()
    logger.info("Seeded %d section mappings (%d inserted, %d updated/skipped)", len(mappings), inserted, skipped)
    print(f"Section mappings: {inserted} inserted, {skipped} already existed. Total = {len(mappings)}")


if __name__ == "__main__":
    run()
