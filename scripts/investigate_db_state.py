import psycopg
from psycopg import sql

URL = "postgresql://campus_user:@127.0.0.1:5433/campus_ai_test"

with psycopg.connect(URL) as conn:
    with conn.cursor() as cur:
        for s in ['test_schema', 'public']:
            cur.execute(sql.SQL("SELECT table_name FROM information_schema.tables WHERE table_schema={};").format(sql.Literal(s)))
            tables = [r[0] for r in cur.fetchall()]
            print(f"\n--- Schema {s} ({len(tables)} tables) ---")
            for t in ['timetables', 'timetable_versions', 'timetable_entries', 'audit_logs']:
                if t in tables:
                    cur.execute(sql.SQL("SELECT COUNT(*) FROM {}.{};").format(sql.Identifier(s), sql.Identifier(t)))
                    res = cur.fetchone()
                    if res:
                        print(f"  {s}.{t}: {res[0]}")
                    cur.execute(sql.SQL("SELECT column_name FROM information_schema.columns WHERE table_schema={} AND table_name={};").format(sql.Literal(s), sql.Literal(t)))
                    cols = [c[0] for c in cur.fetchall()]
                    print(f"   cols: {cols}")
                    cur.execute(sql.SQL("SELECT * FROM {}.{} LIMIT 5;").format(sql.Identifier(s), sql.Identifier(t)))
                    for row in cur.fetchall():
                        print("   row:", row)
