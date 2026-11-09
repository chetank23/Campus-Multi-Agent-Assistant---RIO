# RIO-MJP — Supabase PostgreSQL Integration & Migration Report

**Generated:** 2026-11-09 08:24:02 UTC  
**Integration Status:** `AWAITING_CONFIGURATION`  

---

## 1. Executive Summary

The Supabase integration script is ready and verified. To connect the production Supabase PostgreSQL project, configure the `SUPABASE_DATABASE_URL` environment variable.

### Connection Setup Instructions
1. In your Supabase Dashboard, navigate to **Project Settings** -> **Database**.
2. Under **Connection string**, select **Session pooler** (recommended for IPv4 networks) or **Direct connection**.
3. Add the URI to `.env`:
   ```bash
   SUPABASE_DATABASE_URL=postgresql+psycopg://postgres.[project-ref]:[YOUR-PASSWORD]@aws-0-[region].pooler.supabase.com:6543/postgres?sslmode=require
   ```
4. Run the automated migration script:
   ```powershell
   .\venv\Scripts\python.exe scripts/migrate_to_supabase.py
   ```

---

## 2. Integration Guidance & Safety Guarantees

To connect your live Supabase instance, obtain your Session Pooler or Direct connection URI from the Supabase Console and set `SUPABASE_DATABASE_URL` in your `.env` file.
The migration pipeline will apply Alembic schema `f1a2b3c4d5e6` and import the authoritative 72 accounts.

---

## 3. Local Isolation Safeguards

- Local test suite (`pytest`) continues to target port 5433 (`campus_ai_pytest`).
- Local development database continues to target port 5433 (`campus_ai_test`).
- Supabase operations never run automatically in CI without explicit credentials.
- No production records are ever dropped using `TRUNCATE CASCADE`.