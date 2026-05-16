from backend.database.mysql import get_mysql_connection

def add_raw_html_column():
    conn = get_mysql_connection()
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE ecourts_case_status ADD COLUMN raw_html LONGTEXT")
        conn.commit()
        print("Column raw_html added.")
    except Exception as e:
        print(f"Column probably exists: {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    add_raw_html_column()
