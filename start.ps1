<#
.SYNOPSIS
    One-command startup script for RIO-MJP (PostgreSQL, Backend, and Frontend).
#>

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "            Starting RIO-MJP Campus Assistant             " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Verify / Start PostgreSQL
Write-Host "[1/3] Checking PostgreSQL database service..." -ForegroundColor Yellow
$pgService = Get-Service -Name "postgresql-x64-18" -ErrorAction SilentlyContinue

if ($null -eq $pgService) {
    Write-Host "WARNING: Service 'postgresql-x64-18' not found. Checking port 5432 directly..." -ForegroundColor DarkYellow
} elseif ($pgService.Status -ne "Running") {
    Write-Host "Starting Windows Service 'postgresql-x64-18'..." -ForegroundColor Yellow
    try {
        Start-Service -Name "postgresql-x64-18"
        Write-Host "PostgreSQL service started successfully." -ForegroundColor Green
    } catch {
        Write-Host "Could not start PostgreSQL service automatically (Administrator privileges may be required)." -ForegroundColor Red
        Write-Host "Please start it manually or run PowerShell as Administrator." -ForegroundColor Red
    }
} else {
    Write-Host "PostgreSQL service is running." -ForegroundColor Green
}

# Quick non-destructive connectivity check
try {
    & "$ProjectRoot\venv\Scripts\python.exe" -c "from backend.config import engine; from sqlalchemy import text; c = engine.connect(); c.execute(text('SELECT 1')); c.close()" 2>$null
    Write-Host "PostgreSQL database connection verified." -ForegroundColor Green
} catch {
    Write-Host "Warning: Could not connect to database. Ensure PostgreSQL is listening on port 5432." -ForegroundColor DarkYellow
}

# 2. Launch Backend in a dedicated window
Write-Host ""
Write-Host "[2/3] Launching Backend (FastAPI / Uvicorn)..." -ForegroundColor Yellow
$backendCmd = @"
`$host.UI.RawUI.WindowTitle = 'RIO-MJP — Backend (Port 8000)'
cd '$ProjectRoot'
Write-Host '==================================================' -ForegroundColor Cyan
Write-Host '          RIO-MJP FASTAPI BACKEND SERVER          ' -ForegroundColor Cyan
Write-Host '  API:  http://127.0.0.1:8000                     ' -ForegroundColor Cyan
Write-Host '  Docs: http://127.0.0.1:8000/docs                ' -ForegroundColor Cyan
Write-Host '==================================================' -ForegroundColor Cyan
Write-Host ''
.\venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd

# 3. Launch Frontend in a dedicated window
Write-Host "[3/3] Launching Frontend (React / Vite)..." -ForegroundColor Yellow
$frontendCmd = @"
`$host.UI.RawUI.WindowTitle = 'RIO-MJP — Frontend (Port 5173)'
cd '$ProjectRoot\frontend'
Write-Host '==================================================' -ForegroundColor Green
Write-Host '           RIO-MJP REACT VITE FRONTEND            ' -ForegroundColor Green
Write-Host '  App:  http://localhost:5173/                    ' -ForegroundColor Green
Write-Host '==================================================' -ForegroundColor Green
Write-Host ''
npm run dev
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "  RIO-MJP is launching in separate labeled windows!       " -ForegroundColor Green
Write-Host "  • Frontend: http://localhost:5173                       " -ForegroundColor Green
Write-Host "  • Backend:  http://127.0.0.1:8000                       " -ForegroundColor Green
Write-Host "  • Docs:     http://127.0.0.1:8000/docs                  " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host ""
