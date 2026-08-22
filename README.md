# Multi-Agent Campus Assistant & Automated Timetable Engine

Capstone project — Center for Intelligent Enterprise Systems.

## Quick Start

See the Development Roadmap in `CAPSTONE_SYSTEM_BLUEPRINT.md.md` (§20).

### Stage 1 — Database Setup

```powershell
# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate

# Install Stage-1 dependencies
pip install -r requirements.txt

# Copy and edit environment file
copy .env.example .env
# Edit .env: set DATABASE_URL with your campus_user password

# Run migrations
cd backend
alembic upgrade head
```
