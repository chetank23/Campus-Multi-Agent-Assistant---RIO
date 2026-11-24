# RIO-MJP: Complete Local Setup & Deployment Guide

This guide provides end-to-end instructions for setting up, configuring, running, and verifying the **RIO-MJP (Campus Multi-Agent Assistant & Automated Timetable Engine)** system.

---

## 📋 System Prerequisites

Ensure the following tools are installed on your machine:
- **Python**: Version 3.11 or 3.13
- **Node.js**: Version 18+ and **npm**
- **PostgreSQL**: Version 15+ (PostgreSQL 18 tested and verified)
- **Redis** *(Optional for local development; required for multi-worker distributed queues)*

---

## 🗄️ Step 1 — Database Setup

### 1. Start PostgreSQL
Ensure the PostgreSQL service or local cluster is active. If running a custom local instance on port `5433`:
```powershell
& "C:\Program Files\PostgreSQL\18\bin\postgres.exe" -D ".\test_pg_5433"
```

### 2. Create Required Databases and User
Connect to PostgreSQL (`psql -U postgres`) and run:
```sql
CREATE DATABASE campus_ai_test;
CREATE DATABASE campus_ai_pytest;
CREATE USER campus_user WITH ENCRYPTED PASSWORD 'CampusPass123';
GRANT ALL PRIVILEGES ON DATABASE campus_ai_test TO campus_user;
GRANT ALL PRIVILEGES ON DATABASE campus_ai_pytest TO campus_user;
```

---

## 🐍 Step 2 — Backend Setup

### 1. Create Virtual Environment
```powershell
python -m venv venv
.\venv\Scripts\activate
```

### 2. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env` (or configure your active environment):
```dotenv
DATABASE_URL=postgresql://campus_user:CampusPass123@localhost:5433/campus_ai_test?options=-csearch_path%3Dtest_schema
TEST_DATABASE_URL=postgresql://campus_user:CampusPass123@localhost:5433/campus_ai_pytest?options=-csearch_path%3Dtest_schema
SECRET_KEY=dev-secret-key-replace-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7
ENVIRONMENT=development
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
```
> **Note:** If Redis is not running locally, the system automatically falls back to synchronous eager execution (`CELERY_TASK_ALWAYS_EAGER=True`), ensuring seamless local development without external dependencies.

### 4. Run Database Migrations
```powershell
alembic upgrade head
```

### 5. Seed Core Reference & Enterprise Data
```powershell
# Populate baseline academic hierarchy, sample Dataset A, placement drives, clubs, and events
python scripts/seed_placements_and_events.py
```

### 6. Start FastAPI Backend Server
```powershell
.\venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
API Documentation will be accessible at:
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

---

## ⚡ Step 3 — Background Workers (Celery + Redis)

When running with an external Redis instance:

### 1. Start Redis
```powershell
redis-server
```

### 2. Start Celery Worker
```powershell
.\venv\Scripts\celery -A backend.celery_app.celery worker --loglevel=info --pool=solo
```

---

## 🎨 Step 4 — Frontend Setup

### 1. Install Dependencies
```powershell
cd frontend
npm install
```

### 2. Run Vite Development Server
```powershell
npm run dev
```
The React application will be available at `http://localhost:5173`.

---

## 🔑 Default Provisioned Credentials

The seed script provisions test accounts for each institutional role:

| Role | Email | Password | Primary Portal Route |
| :--- | :--- | :--- | :--- |
| **Super Admin** | `superadmin@campus.edu` | `Test@1234` | `/super-admin` |
| **Admin** | `admin@campus.edu` | `Admin#RioLocal26` | `/admin` |
| **Faculty** | `aarthy.g@rio-mjp.test` | `Aarthyg#RioLocal26` | `/faculty` |
| **Student** | `r23eh002@rio-mjp.test` | `R23eh002#RioLocal26` | `/student` |

---

## 🧪 Step 5 — Verification & Testing

### 1. Backend Automated Tests (Pytest)
```powershell
.\venv\Scripts\python.exe -m pytest tests
```

### 2. Frontend Linting & Build Verification
```powershell
cd frontend
npm run lint
npm run build
```

### 3. Multi-Role Dashboard Verification
```powershell
.\venv\Scripts\python.exe scripts/verify_dashboard_headings.py
```
