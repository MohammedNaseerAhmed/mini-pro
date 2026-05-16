import json
import logging
from backend.database.mysql import get_mysql_connection

def seed_authoritative_mappings():
    # Authoritative mapping subset based on your provided JSON
    mappings = [
        {"old_act": "IPC", "old_sec": "302", "old_title": "Murder", "new_act": "BNS", "new_sec": "101", "new_title": "Murder", "type": "retained", "notes": "Definition and punishment identical."},
        {"old_act": "IPC", "old_sec": "376", "old_title": "Rape", "new_act": "BNS", "new_sec": "64", "new_title": "Sexual assault", "type": "modified", "notes": "MAJOR CHANGE: Terminology changed. Aggravated forms now separate."},
        {"old_act": "IPC", "old_sec": "420", "old_title": "Cheating", "new_act": "BNS", "new_sec": "318(4)", "new_title": "Cheating — aggravated", "type": "merged", "notes": "IPC 415 and 420 merged into single BNS 318 with sub-clauses."},
        {"old_act": "IPC", "old_sec": "124A", "old_title": "Sedition", "new_act": "BNS", "new_sec": "152", "new_title": "Acts endangering sovereignty", "type": "replaced", "notes": "Sedition repealed. Replaced by broader provision covering armed rebellion."},
        {"old_act": "CrPC", "old_sec": "438", "old_title": "Anticipatory bail", "new_act": "BNSS", "new_sec": "482", "new_title": "Anticipatory bail", "type": "modified", "notes": "90-day outer limit removed. Can continue till end of trial."},
        {"old_act": "IEA", "old_sec": "65B", "old_title": "Electronic records", "new_act": "BSA", "new_sec": "57/58", "new_title": "Electronic record certificate", "type": "modified", "notes": "CRITICAL: Arjun Panditrao ruling codified. Certificate rule simplified."}
    ]
    
    conn = get_mysql_connection()
    cur = conn.cursor()
    try:
        # Create tables first (subset of your schema for the demo)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS section_mappings (
                id INT AUTO_INCREMENT PRIMARY KEY,
                old_act VARCHAR(10), old_section VARCHAR(20), old_title VARCHAR(200),
                new_act VARCHAR(10), new_section VARCHAR(20), new_title VARCHAR(200),
                change_type VARCHAR(20), change_notes TEXT,
                UNIQUE KEY uk_mapping (old_act, old_section, new_act, new_section)
            )
        """)
        
        for m in mappings:
            cur.execute("""
                INSERT IGNORE INTO section_mappings 
                (old_act, old_section, old_title, new_act, new_section, new_title, change_type, change_notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (m["old_act"], m["old_sec"], m["old_title"], m["new_act"], m["new_sec"], m["new_title"], m["type"], m["notes"]))
        conn.commit()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    seed_authoritative_mappings()
