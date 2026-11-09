from backend.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
query = "SELECT table_name FROM information_schema.tables WHERE table_schema = 'test_schema' AND table_type = 'BASE TABLE' ORDER BY table_name;"
tables = [row[0] for row in db.execute(text(query)).fetchall()]

print(f"Total tables: {len(tables)}")
for t in tables:
    cnt = db.execute(text(f'SELECT count(*) FROM test_schema."{t}"')).scalar()
    if cnt > 0:
        print(f"  {t:35}: {cnt}")
db.close()

