import os
import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from alembic.config import Config
from alembic import command
import urllib.parse

load_dotenv(".env")
original_url = os.environ.get("DATABASE_URL", "")

if "options=" not in original_url:
    if "?" in original_url:
        test_url = original_url + "&options=-csearch_path=test_schema"
    else:
        test_url = original_url + "?options=-csearch_path=test_schema"
    os.environ["DATABASE_URL"] = test_url
else:
    test_url = original_url

@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    engine = create_engine(original_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS test_schema CASCADE"))
        conn.execute(text("CREATE SCHEMA test_schema"))
            
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", test_url)
    command.upgrade(alembic_cfg, "head")
    
    # Seed the database for tests
    import subprocess
    import sys
    env = os.environ.copy()
    env["TEST_PASSWORD"] = "Test@1234"
    subprocess.run([sys.executable, "scripts/seed_database.py", "--dataset", "A"], env=env, check=True)
    
    # Reset sequences for test_schema
    with engine.begin() as conn:
        conn.execute(text("""
            DO $$
            DECLARE
                seq RECORD;
            BEGIN
                FOR seq IN 
                    SELECT c.relname as seq_name, t.relname as table_name 
                    FROM pg_class c 
                    JOIN pg_depend d ON d.objid = c.oid 
                    JOIN pg_class t ON d.refobjid = t.oid 
                    JOIN pg_namespace n ON n.oid = c.relnamespace 
                    WHERE c.relkind = 'S' AND n.nspname = 'test_schema'
                LOOP
                    EXECUTE 'SELECT setval(''test_schema.' || seq.seq_name || ''', COALESCE((SELECT MAX(id) FROM test_schema.' || seq.table_name || '), 1), true)';
                END LOOP;
            END $$;
        """))
    
    yield
