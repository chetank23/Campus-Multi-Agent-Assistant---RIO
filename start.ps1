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
Write-Host "[1/3] Checking PostgreSQL database service (port 5433)..." -ForegroundColor Yellow
$pgData = "$ProjectRoot\test_pg_5433"
$pgCtl = "C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe"

$isListening = $false
try {
    $tcp = Test-NetConnection -Port 5433 -ComputerName 127.0.0.1 -WarningAction SilentlyContinue -InformationLevel Quiet
    if ($tcp) { $isListening = $true }
}
catch {}

if ($isListening) {
    Write-Host "PostgreSQL is running and listening on port 5433." -ForegroundColor Green
}
else {
    Write-Host "Starting PostgreSQL cluster on port 5433..." -ForegroundColor Yellow
    if (Test-Path $pgCtl) {
        & $pgCtl start -D $pgData -l "$pgData\postgres.log"
        Start-Sleep -Seconds 2
    }
    else {
        Start-Process "C:\Program Files\PostgreSQL\18\bin\postgres.exe" -ArgumentList "-D", "`"$pgData`"" -WindowStyle Hidden
        Start-Sleep -Seconds 2
    }
}

# Quick non-destructive connectivity check
try {
    & "$ProjectRoot\venv\Scripts\python.exe" -c "import psycopg; conn = psycopg.connect('postgresql://campus_user:@127.0.0.1:5433/campus_ai_test?options=-csearch_path%3Dtest_schema'); cur = conn.cursor(); cur.execute('SELECT 1'); conn.close()" 2>$null
    Write-Host "PostgreSQL database connection verified." -ForegroundColor Green
}
catch {
    Write-Host "Warning: Could not connect to database on port 5433. Check $pgData\postgres.log." -ForegroundColor DarkYellow
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
