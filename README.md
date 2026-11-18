# RIO-MJP: Multi-Agent Campus Assistant & Academic Management Engine

[![CI Pipeline](https://github.com/chetank23/Campus-Multi-Agent-Assistant---RIO/actions/workflows/ci.yml/badge.svg)](https://github.com/chetank23/Campus-Multi-Agent-Assistant---RIO/actions/workflows/ci.yml)
[![CodeQL Security](https://github.com/chetank23/Campus-Multi-Agent-Assistant---RIO/actions/workflows/codeql.yml/badge.svg)](https://github.com/chetank23/Campus-Multi-Agent-Assistant---RIO/actions/workflows/codeql.yml)
[![Live NVIDIA NIM Acceptance](https://github.com/chetank23/Campus-Multi-Agent-Assistant---RIO/actions/workflows/nvidia-live-acceptance.yml/badge.svg)](https://github.com/chetank23/Campus-Multi-Agent-Assistant---RIO/actions/workflows/nvidia-live-acceptance.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![React: 19](https://img.shields.io/badge/react-19-61dafb.svg)](https://react.dev/)
[![Alembic: Head](https://img.shields.io/badge/alembic-f1a2b3c4d5e6-green.svg)](alembic/)

---

## 1. Executive Summary & Project Overview

**RIO-MJP** is an enterprise-grade academic management system and autonomous multi-agent campus assistant. Developed at the **Center for Intelligent Enterprise Systems**, RIO-MJP resolves complex institutional scheduling, academic resource optimization, curriculum lifecycle governance, and contextual campus inquiry routing.

The platform unites a **deterministic constraint-satisfaction engine** (powered by Google OR-Tools CP-SAT) for automated multi-semester timetable generation with a **grounded multi-agent conversational AI** (powered by NVIDIA Nemotron 3 Ultra 550B via NVIDIA NIM). The architecture enforces strict role-based access control, cryptographic session handling, and transactional database integrity across 54 relational tables.

---

## 2. System Architecture

The system is architected as an asynchronous, decoupled multi-tier web application:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        CLIENT / PRESENTATION LAYER                     │
│  React 19 + TypeScript + Vite + Tailwind CSS + TanStack Query v5       │
│  Role-Guarded Dashboards: SUPER_ADMIN | ADMIN | FACULTY | STUDENT      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTPS / HTTP-Only Cookies (JWT)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        API & ORCHESTRATION LAYER                       │
│  FastAPI (Uvicorn) + Pydantic v2 + Python 3.12/3.13                    │
│  - JWT Bearer Authentication + Rate-Limiting Middleware                │
│  - 28 REST Route Modules (Academics, Resources, Timetables, etc.)      │
└───────────────┬───────────────────┬───────────────────┬────────────────┘
                │                   │                   │
                ▼                   ▼                   ▼
┌─────────────────────────┐ ┌─────────────────┐ ┌─────────────────────────┐
│  AI ASSISTANT SUBSYSTEM │ │  OPTIMIZER CORE │ │   DATA & PERSISTENCE    │
│  - NVIDIA NIM Provider  │ │  - Google       │ │  - PostgreSQL 18        │
│    (Nemotron 3 Ultra)   │ │    OR-Tools     │ │    (54 relational       │
│  - Reusable HTTP Pool   │ │    CP-SAT       │ │    tables)              │
│  - Grounded Tool Calls  │ │  - Deterministic│ │  - Alembic Migrations   │
│  - Deterministic Answer │ │    Validator    │ │    (Head: f1a2b3c4d5e6) │
│    Synthesis Fallback   │ │  - Soft Scorer  │ │  - SQLAlchemy 2.0 ORM   │
└─────────────────────────┘ └─────────────────┘ └─────────────────────────┘
```

---

## 3. Technology Stack

| Layer | Component | Version / Specification | Rationale & Purpose |
|---|---|---|---|
| **Backend Framework** | FastAPI | `^0.115.0` | Asynchronous high-throughput ASGI REST API with Pydantic v2 validation |
| **Backend Runtime** | Python | `3.12` / `3.13` | Modern typing, high performance, native datetime timezone handling |
| **Database** | PostgreSQL | `18.x` | ACID compliance, schema isolation, foreign key constraints, JSONB |
| **Database Migrations** | Alembic | `^1.14.0` | Strict programmatic versioning across 54 relational schema tables |
| **ORM Layer** | SQLAlchemy | `^2.0.36` | Strict mapped-column typing, relationship integrity, connection pooling |
| **Constraint Solver** | Google OR-Tools | `^9.11.0` | CP-SAT solver for timetable conflict resolution and capacity optimization |
| **AI LLM Provider** | NVIDIA NIM | Nemotron 3 Ultra 550B | Grounded database tool execution with fallback synthesis |
| **Frontend Framework** | React | `19.2.8` | Component-based UI with React Compiler compliance and zero render ref access |
| **Frontend Language** | TypeScript | `~6.0.2` | Compile-time type safety across API contracts and component props |
| **Build Tooling** | Vite | `^8.3.0` | Dynamic code splitting, manual chunk separation, < 150 kB entry bundle |
| **State & Cache** | TanStack Query | `^5.64.2` | Optimistic mutations, background revalidation, query cache deduplication |
| **Styling & Icons** | Tailwind CSS + Lucide | `3.4.17` / `0.469.0` | Utility-first responsive design system with role-specific color hierarchies |
| **Automated Testing** | Pytest & Playwright | `9.1.1` / `1.42.0` | 623 backend tests and 10 end-to-end browser user journey suites |
| **Static Analysis** | Oxlint, Pyrefly, Pyright | Latest | Zero-tolerance static typing, linting, and AST code safety checks |

---

## 4. Repository Directory Structure

```
RIO-MJP/
├── .github/                      # GitHub Actions workflows & automation
│   ├── dependabot.yml            # Automated pip, npm & actions dependency updates
│   └── workflows/
│       ├── ci.yml                # Master 5-tier PR & push validation pipeline
│       ├── codeql.yml            # CodeQL AST Static Application Security Testing
│       ├── deploy.yml            # Staging/Production continuous deployment
│       └── nvidia-live-acceptance.yml # Secret-gated live NVIDIA NIM test runner
├── alembic/                      # Database migration scripts
│   ├── env.py                    # Migration runtime & schema hook
│   └── versions/                 # Versioned migration revision files (Head: f1a2b3c4d5e6)
├── agents/                       # Autonomous campus AI assistant
│   ├── llm/
│   │   └── nvidia_provider.py    # Reusable HTTP connection-pooled NVIDIA NIM client
│   └── coordinator/              # Intent routing and tool execution coordinators
├── backend/                      # FastAPI core application
│   ├── main.py                   # FastAPI ASGI entrypoint, CORS & middleware config
│   ├── config.py                 # Pydantic v2 application settings & secret management
│   ├── database.py               # Engine, connection pooling & SessionLocal factories
│   ├── dependencies.py           # Database session & security dependency injection
│   ├── core/
│   │   └── security.py           # Password hashing, JWT token creation & verification
│   ├── models/                   # SQLAlchemy 2.0 mapped domain entities (54 tables)
│   ├── optimizer/                # OR-Tools timetable solver, scorer & validator
│   ├── routes/                   # 28 REST API endpoint routers
│   ├── schemas/                  # Pydantic v2 request/response schemas
│   └── services/                 # Core domain business logic services
├── data/                         # Sample datasets and extraction assets
│   └── sample/A/                 # Standard institutional test dataset
├── frontend/                     # React 19 + TypeScript single-page application
│   ├── src/
│   │   ├── auth/                 # Auth context, route guards & session storage
│   │   ├── components/           # Reusable UI components & layouts
│   │   ├── context/              # Toast context & application state
│   │   ├── hooks/                # Data refresh & operational custom hooks
│   │   ├── pages/                # Role-specific dashboard views (SuperAdmin, Admin, Faculty, Student)
│   │   └── routes/               # Code-split dynamic routes with Suspense fallback
│   ├── package.json              # Frontend npm dependencies
│   └── vite.config.ts            # Vite build configuration & chunk splitting rules
├── reports/                      # Authoritative audit and release verification reports
│   ├── RELEASE_STATUS_REPORT.md  # Official 14-module release status matrix
│   └── screenshots/              # E2E test execution visual artifacts
├── scripts/                      # Operational automation, seeding & audit scripts
│   ├── audit_database_state.py   # PostgreSQL read-only table & FK integrity inspector
│   ├── benchmark_nemotron.py     # NVIDIA NIM provider latency & tool calling benchmark
│   ├── scan_secrets.py           # Pre-commit zero-secret credential scanner
│   └── seed_database_a.py        # Institutional dataset seeder
├── tests/                        # Comprehensive test suite (623+ tests)
│   ├── conftest.py               # Pytest database fixtures, test client & mocks
│   ├── e2e/                      # Playwright browser acceptance tests (10 journeys)
│   ├── integration/              # Real NVIDIA NIM live integration test suite
│   └── unit/                     # Unit tests for models, routes, services & optimizer
├── alembic.ini                   # Alembic environment configuration
├── pytest.ini                    # Pytest configuration, coverage thresholds & markers
└── requirements.txt              # Pinned Python production dependencies
```

---

## 5. Four-Role Access Model (RBAC)

The system enforces strict multi-tenant role isolation at both the backend authorization barrier and frontend route-guard level:

```
┌────────────────────────────────────────────────────────────────────────┐
│                          INSTITUTIONAL ROLES                           │
├───────────────┬──────────────────────────────────┬─────────────────────┤
│ Role          │ Scope of Authority               │ Portal Route Base   │
├───────────────┼──────────────────────────────────┼─────────────────────┤
│ SUPER_ADMIN   │ System-wide governance, Academic │ /super-admin        │
│               │ Regulations, Cohorts, Curriculum │                     │
│               │ Versions, PDF Extraction & Audit │                     │
├───────────────┼──────────────────────────────────┼─────────────────────┤
│ ADMIN         │ Departmental operations, Faculty │ /admin              │
│               │ allocation, Timetable generation,│                     │
│               │ Room booking, Change requests    │                     │
├───────────────┼──────────────────────────────────┼─────────────────────┤
│ FACULTY       │ Personal schedules, Teaching     │ /faculty            │
│               │ availability, Leave substitution │                     │
│               │ requests, Event hosting          │                     │
├───────────────┼──────────────────────────────────┼─────────────────────┤
│ STUDENT       │ Enrolled timetable, Personal     │ /student            │
│               │ course lists, Placement drives,  │                     │
│               │ Campus events, AI inquiries      │                     │
└───────────────┴──────────────────────────────────┴─────────────────────┘
```

---

## 6. Local Development Setup & Prerequisites

Ensure the following tools are installed on your host machine:
- **Python**: Version `3.12` or `3.13`
- **Node.js**: Version `20.x` or `22.x` (with `npm 10+`)
- **PostgreSQL**: Version `18.x`
- **Git**: Version `2.40+`

---

## 7. Backend Installation & Environment Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/chetank23/Campus-Multi-Agent-Assistant---RIO.git
   cd Campus-Multi-Agent-Assistant---RIO
   ```

2. **Initialize Python virtual environment:**
   ```bash
   python -m venv venv
   # Windows (PowerShell)
   .\venv\Scripts\Activate.ps1
   # Linux/macOS
   source venv/bin/activate
   ```

3. **Install pinned dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   playwright install chromium
   ```

4. **Configure environment variables:**
   Copy `.env.example` to `.env`:
   ```bash
   copy .env.example .env
   ```
   Configure the required variables in `.env`:
   ```ini
   DATABASE_URL=postgresql://campus_user:your_password@127.0.0.1:5433/campus_ai_test
   SECRET_KEY=generate-a-secure-random-64-character-hex-string
   ALGORITHM=HS256
   ACCESS_TOKEN_EXPIRE_MINUTES=30
   REFRESH_TOKEN_EXPIRE_DAYS=7
   ENVIRONMENT=development
   CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

   # AI Assistant (NVIDIA NIM)
   NVIDIA_API_KEY=nvapi-your-key-here
   NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
   NVIDIA_MODEL_ID=nvidia/nemotron-3-ultra-550b
   ```

---

## 8. Database Setup, Migrations & Seed Data

1. **Create the PostgreSQL database:**
   Ensure PostgreSQL is running on the configured port (e.g., port 5433 or 5432):
   ```sql
   CREATE USER campus_user WITH PASSWORD 'your_password';
   CREATE DATABASE campus_ai_test OWNER campus_user;
   GRANT ALL PRIVILEGES ON DATABASE campus_ai_test TO campus_user;
   ```

2. **Execute Alembic schema migrations:**
   Run migrations from the project root to bring schema up to head (`f1a2b3c4d5e6`):
   ```bash
   alembic upgrade head
   ```

3. **Verify database state:**
   Inspect table counts and foreign key integrity:
   ```bash
   python scripts/audit_database_state.py
   ```

4. **Seed institutional dataset:**
   Load standard Dataset A (departments, programs, faculty, students, courses, rooms):
   ```bash
   python scripts/seed_database_a.py
   ```

---

## 9. Frontend Installation & Production Build

1. **Install Node dependencies:**
   ```bash
   npm --prefix frontend install
   ```

2. **Run frontend static checks:**
   ```bash
   npm --prefix frontend run lint
   ```
   *Expected result: 0 warnings, 0 errors.*

3. **Build optimized production bundle:**
   ```bash
   npm --prefix frontend run build
   ```
   *Result: Code-split chunks with dynamic import and vendor extraction (all chunks < 300 kB, entry bundle < 140 kB).*

4. **Start frontend development server:**
   ```bash
   npm --prefix frontend run dev
   ```
   The application is accessible at `http://localhost:5173`.

---

## 10. Automated Testing & Verification

The project enforces continuous verification with zero tolerance for broken tests or warnings:

### Backend Tests
Execute the complete backend test suite:
```bash
pytest -v
```
To run targeted unit tests:
```bash
pytest tests/unit/
```

### Static Type Checking
Verify type safety using Pyrefly or Pyright:
```bash
.\venv\Scripts\pyrefly.bat check --min-severity=warn
```

### Pre-Commit Secret Scanner
Audit the repository for leaked tokens or credentials:
```bash
python scripts/scan_secrets.py
```

### End-to-End Browser Acceptance Tests
Start backend and frontend, then run Playwright browser journeys:
```bash
pytest -v -m browser tests/e2e/test_browser_acceptance.py
```

---

## 11. CI/CD Architecture & Workflows

Automated continuous integration is orchestrated via **GitHub Actions**:

- **PR Validation Pipeline (`.github/workflows/ci.yml`)**:
  - `backend`: Checks Python 3.12, installs dependencies, spins up PostgreSQL service, runs migrations, executes full pytest suite with JUnit reporting.
  - `migrations`: Validates two-way migration idempotency (`upgrade head -> downgrade base -> upgrade head`).
  - `frontend`: Installs npm dependencies, runs `oxlint` (enforcing 0 errors, 0 warnings), executes TypeScript check and production bundle build.
  - `browser-acceptance`: Executes Playwright headless Chromium e2e tests against live dev servers.
  - `security`: Runs `pip-audit`, `npm audit`, and `scripts/scan_secrets.py`.

- **AST Security Analysis (`.github/workflows/codeql.yml`)**:
  - Nightly and PR CodeQL static application security testing for Python and JavaScript/TypeScript.

- **Automated Dependencies (`.github/dependabot.yml`)**:
  - Weekly checks for `pip`, `npm`, and `github-actions` updates.

- **Live NVIDIA NIM Integration (`.github/workflows/nvidia-live-acceptance.yml`)**:
  - Secret-gated workflow verifying live connectivity to NVIDIA NIM API with token latency capture.

---

## 12. Deployment Guide

### Frontend Deployment (Netlify)
- **Base directory:** `frontend`
- **Build command:** `npm run build`
- **Publish directory:** `frontend/dist`
- **Environment variables:**
  - `VITE_API_BASE_URL`: Production backend API base URL (e.g., `https://api.rio-campus.edu`).

### Backend Deployment (Render / Docker)
- **Runtime:** Python 3.12 (or Docker container)
- **Start command:** `uvicorn backend.main:app --host 0.0.0.0 --port 8000`
- **Pre-deploy command:** `alembic upgrade head`
- **Environment variables:**
  - `DATABASE_URL`: Managed PostgreSQL connection string.
  - `SECRET_KEY`: High-entropy JWT signing key.
  - `NVIDIA_API_KEY`: NVIDIA NIM API production key.
  - `CORS_ORIGINS`: Production frontend origin URL.

---

## 13. Historical Documentation Reconciliation

During development, architectural decisions evolved. Use this matrix to interpret older documentation and reports in `reports/` and `documentation/`:

| Topic / Artifact | Historical Status (Deprecated) | Current Production Truth |
|---|---|---|
| **Database Engine** | Supabase (referenced in early logs) | **PostgreSQL 18** on dedicated local/container instance managed via **Alembic** (`f1a2b3c4d5e6`). |
| **Role Hierarchy** | 5 roles (Student, Faculty, HOD, Coordinator, Admin) | **4 Canonical Roles**: `SUPER_ADMIN`, `ADMIN`, `FACULTY`, `STUDENT`. Multi-level review chains consolidated under Admin/Super Admin. |
| **LLM Provider** | Mock / Generic OpenAI API | **NVIDIA NIM** (`nvidia/nemotron-3-ultra-550b`) with connection pooling and deterministic synthesis fallback. |
| **Frontend Bundle** | Monolithic 1.1 MB `index.js` bundle | **Code-split dynamic routes** (< 140 kB entry bundle, all vendor chunks < 300 kB). |
| **Lint Status** | 4 React Compiler / Fast Refresh warnings | **0 warnings, 0 errors** across all 143 frontend source files via `oxlint`. |
| **Test Baseline** | 590 backend tests | **623 backend tests** passing with 10 automated Playwright browser journeys. |

---

## 14. Troubleshooting

- **PostgreSQL Connection Refused on Port 5432 / 5433:**
  - Check active ports with `Get-NetTCPConnection -LocalPort 5432,5433`.
  - Ensure `.env` references the correct active instance port.
- **Vite Fast Refresh Warning:**
  - Always separate React component declarations from custom hook functions (e.g., keep hooks in `src/hooks/` and types in `.ts` files).
- **Alembic Target Schema Mismatch:**
  - Set `SCHEMA_NAME=public` or `test_schema` matching your database environment before running migrations.
- **NVIDIA NIM API Quota / Timeout:**
  - If live API access is throttled, the assistant automatically falls back to deterministic database-grounded synthesis without exposing raw stack traces.

---

## 15. Authors & Acknowledgments

- **Development Team:** Lead Implementation & Architecture Engineering
- **Innovation Center:** Center for Intelligent Enterprise Systems
- **Repository:** [chetank23/Campus-Multi-Agent-Assistant---RIO](https://github.com/chetank23/Campus-Multi-Agent-Assistant---RIO)
