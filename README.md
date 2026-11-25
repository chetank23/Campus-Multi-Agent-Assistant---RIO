# RIO-MJP: Multi-Agent Campus Assistant & Automated Timetable Engine

An enterprise-grade Academic ERP, Automated Timetable Engine, and Multi-Agent Assistant designed for modern universities. The system integrates deterministic constraint optimization (Google OR-Tools CP-SAT), multi-agent conversational intelligence (LangGraph), and an end-to-end responsive React dashboard across four institutional roles.

---

## 🏛️ System Architecture Overview

```
                                  ┌──────────────────────────────┐
                                  │      React 18 + Vite SPA     │
                                  │  (TypeScript + TailwindCSS)  │
                                  └──────────────┬───────────────┘
                                                 │
                                       REST APIs + SSE Events
                                                 │
                                                 ▼
                                  ┌──────────────────────────────┐
                                  │        FastAPI Gateway       │
                                  │  (JWT Auth, HttpOnly Cookies) │
                                  └───────┬──────────────┬───────┘
                                          │              │
                   ┌──────────────────────┴──────┐       │
                   ▼                             ▼       ▼
      ┌─────────────────────────┐   ┌─────────────────────────┐
      │   OR-Tools CP-SAT       │   │  LangGraph Multi-Agent  │
      │   Timetable Engine      │   │  Intelligence System    │
      └────────────┬────────────┘   └────────────┬────────────┘
                   │                             │
                   └──────────────┬──────────────┘
                                  ▼
                   ┌─────────────────────────────┐
                   │    PostgreSQL (Relational)  │
                   │    Alembic Migrations       │
                   └─────────────────────────────┘
```

---

## 👥 Enterprise Portals & User Roles

| Role | Portal Route | Primary Capabilities |
| :--- | :--- | :--- |
| **SUPER_ADMIN** | `/super-admin` | Multi-regulation management, cohort definition, semester credit quotas, curriculum version control, AI syllabus extraction, global audit log history. |
| **ADMIN** | `/admin` | Campus infrastructure (buildings, rooms), academic catalog (departments, programs, batches, sections), faculty & student profiles, CP-SAT timetable generation, placement drive coordination, change requests, notifications. |
| **FACULTY** | `/faculty` | Weekly teaching schedule, department master timetables, teaching availability configuration, campus resource booking, club supervision, leave/substitution management. |
| **STUDENT** | `/student` | Personal timetable, course registrations, CDC placement drive applications & interview tracking, campus events registration, student club memberships, announcements. |

---

## 🚀 Core Implemented Features

### 1. 💼 Placements & Career Development (CDC)
- **Drive Lifecycle**: Creation, publication, postponement, and cancellation of recruitment drives.
- **Eligibility Engine**: Real-time evaluation against minimum CGPA, active backlogs, graduation year, and department restrictions.
- **Candidate Applications**: Students submit direct applications with portfolio/resume links and notes; administrators inspect applicants and update status (`APPLIED`, `SHORTLISTED`, `INTERVIEW_SCHEDULED`, `SELECTED`, `REJECTED`).
- **Selection Timeline**: Multi-round selection schedule builder (Online Assessments, Technical Interviews, HR Rounds) with video links or campus room assignments.

### 2. 🎪 Campus Clubs & Extracurricular Events
- **Clubs Directory**: Student and faculty organizations across Technical, Cultural, Literary, and Sports categories.
- **Memberships**: Students and faculty can join and leave active clubs with role tracking (`MEMBER`, `COORDINATOR`).
- **Events & Hackathons**: Calendar of university workshops, hackathons, and guest lectures with real-time status (`PUBLISHED`, `ONGOING`, `COMPLETED`).
- **Event Registrations**: One-click student registration and cancellation with capacity and target audience validation.

### 3. 📄 Curriculum Upload Security & Extraction
- **Upload Guardrails**: Maximum 25 MB file size enforcement (`413 Request Entity Too Large`).
- **Magic Byte Validation**: Strict PDF header verification (`%PDF-`) preventing spoofed file uploads.
- **Path Traversal Defense**: Safe filename basename extraction strictly constrained to the application's document storage root.

### 4. ⏱️ Automated Timetable Engine (OR-Tools CP-SAT)
- **Constraint Solver**: Mathematical constraint optimization enforcing hard boundaries (no faculty double-booking, room capacity limits, section conflict avoidance) and soft penalties (spread across days, faculty preferences).
- **Multi-Section Scheduling**: Concurrently schedules multi-section batches across shared lab resources and common faculty members without constraint dilution.

### 5. 🔒 Security & RBAC
- **Authentication**: JWT access and refresh tokens transmitted via secure, `HttpOnly`, `SameSite=Lax` cookies.
- **Fine-Grained Permissions**: Strict dependency-level role checks (`require_roles("ADMIN", "SUPER_ADMIN")`).
- **Audit Logging**: Comprehensive logging of administrative actions, curriculum updates, and timetable changes with user attribution and IP recording.

### 6. ⚡ Background Processing & Local Fallback
- **Celery & Eager Fallback**: Supports distributed task queues with Redis. When running locally without Redis, tasks automatically fall back to synchronous eager execution (`task_always_eager = True`), ensuring local development and tests operate seamlessly.

---

## 🛠️ Technology Stack

- **Backend**: Python 3.11+ / 3.13, FastAPI, SQLAlchemy 2.0 (ORM), Alembic, Pydantic v2, Google OR-Tools.
- **Frontend**: React 18, Vite, TypeScript, TailwindCSS, TanStack React Query v5, Lucide Icons.
- **Database**: PostgreSQL 15+ (local or containerized).
- **AI & Optimization**: LangGraph, Google OR-Tools CP-SAT, NVIDIA NIM (optional integration).

---

## 💻 Local Setup & Installation

### Prerequisites
- Python 3.11+ or 3.13
- Node.js 18+ and npm
- PostgreSQL 15+ (running locally)

### 1. Database Setup
Ensure PostgreSQL is running and create the application databases:
```sql
CREATE DATABASE campus_ai_test;
CREATE DATABASE campus_ai_pytest;
CREATE USER campus_user WITH ENCRYPTED PASSWORD 'CampusPass123';
GRANT ALL PRIVILEGES ON DATABASE campus_ai_test TO campus_user;
GRANT ALL PRIVILEGES ON DATABASE campus_ai_pytest TO campus_user;
```

### 2. Backend Setup
```powershell
# Create and activate Python virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
# Copy .env.example to .env and configure DATABASE_URL
# Example: DATABASE_URL=postgresql://campus_user:CampusPass123@localhost:5432/campus_ai_test?options=-csearch_path%3Dtest_schema

# Apply database migrations
alembic upgrade head

# Seed reference data, placement drives, clubs, and events
python scripts/seed_placements_and_events.py

# Start FastAPI backend server
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Frontend Setup
```powershell
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Run Vite development server
npm run dev
```
The application will be live at `http://localhost:5173`.

---

## 🔑 Account Provisioning & Roles

User accounts across institutional roles are provisioned through administrative workflows or development initialization:

- **Super Admin**: System governance, regulation management, curriculum ingestion (`/super-admin`). Initial bootstrap account configured via environment variables.
- **Admin (CDC)**: Institutional timetables, placement drives, campus events, and audit oversight (`/admin`).
- **Faculty**: Department timetable views, substitution requests, and student mentorship (`/faculty`).
- **Student**: Personalized published timetable, placement drive applications, and campus event registrations (`/student`).

To seed initial local development test accounts and reference records:
```powershell
python scripts/seed_placements_and_events.py
```
*Note: In production environments, user credentials and initial administrators must be provisioned via secure directory integration or the Admin Users management portal.*

---

## 🧪 Quality Assurance & Test Verification

### Frontend Verification
```powershell
cd frontend

# Fast lint check (0 warnings, 0 errors)
npm run lint

# Production TypeScript typecheck and bundle build
npm run build
```

### Backend Test Suite
```powershell
# Run backend pytest suite against isolated pytest database
.\venv\Scripts\python.exe -m pytest tests/
```

---

## 📁 Repository Structure

```
├── backend/                  # FastAPI Application
│   ├── models/               # SQLAlchemy 2.0 ORM Models
│   ├── routes/               # API Router Endpoints
│   ├── schemas/              # Pydantic Request/Response Models
│   ├── services/             # Business Logic & Service Layer
│   ├── optimizer/            # OR-Tools CP-SAT Solver Integration
│   ├── celery_app.py         # Celery App with Eager Local Fallback
│   └── main.py               # Application Entry Point
├── frontend/                 # React 18 + Vite Application
│   ├── src/
│   │   ├── api/              # Axios API Client Methods
│   │   ├── components/       # Reusable UI & Layout Components
│   │   ├── context/          # React Contexts (Auth, Toast)
│   │   ├── pages/            # Role-Specific Dashboard Pages
│   │   └── routes/           # AppRoutes with React.lazy Code Splitting
├── database/migrations/      # Alembic Version Scripts
├── scripts/                  # Database Seed & Maintenance Utilities
└── tests/                    # Pytest Integration & Unit Test Suite
```

---

## 📄 License
Academic Capstone Project — Center for Intelligent Enterprise Systems.
