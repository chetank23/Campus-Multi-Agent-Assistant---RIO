"""
scripts/db_baseline_inventory.py
--------------------------------
Extracts database table inventory and row counts from campus_ai_test / test_schema.
"""

from sqlalchemy import create_engine, text

DATABASE_URL = "postgresql+psycopg://campus_user:@127.0.0.1:5433/campus_ai_test?options=-csearch_path%3Dtest_schema"

def main():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        tables = conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema='test_schema' ORDER BY table_name")
        ).fetchall()
        print(f"Total tables in test_schema: {len(tables)}")
        for (t,) in tables:
            cnt = conn.execute(text(f'SELECT COUNT(*) FROM test_schema."{t}"')).scalar()
            print(f"  {t}: {cnt}")

if __name__ == "__main__":
    main()

