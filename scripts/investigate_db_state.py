import psycopg

URL = "postgresql://campus_user:@127.0.0.1:5433/campus_ai_test"

with psycopg.connect(URL) as conn:
    with conn.cursor() as cur:
        for s in ['test_schema', 'public']:
            cur.execute(f"SELECT table_name FROM information_schema.tables WHERE table_schema='{s}';")
            tables = [r[0] for r in cur.fetchall()]
            print(f"\n--- Schema {s} ({len(tables)} tables) ---")
            for t in ['timetables', 'timetable_versions', 'timetable_entries', 'audit_logs']:
                if t in tables:
                    cur.execute(f"SELECT COUNT(*) FROM {s}.{t};")
                    print(f"  {s}.{t}: {cur.fetchone()[0]}")
                    cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_schema='{s}' AND table_name='{t}';")
                    cols = [c[0] for c in cur.fetchall()]
                    print(f"   cols: {cols}")
                    cur.execute(f"SELECT * FROM {s}.{t} LIMIT 5;")
                    for row in cur.fetchall():
                        print("   row:", row)
