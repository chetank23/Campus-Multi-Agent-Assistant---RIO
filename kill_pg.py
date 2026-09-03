import psycopg
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from backend.config import DATABASE_URL

psycopg_url = DATABASE_URL.replace("+psycopg", "")
with psycopg.connect(psycopg_url, autocommit=True) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database();")
        db_name = cur.fetchone()[0]
        cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE pid <> pg_backend_pid() AND datname = %s;", (db_name,))
        print(f"Terminated backend processes for database: {db_name}")
