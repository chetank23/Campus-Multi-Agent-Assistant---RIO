"""
run.py — One-command runner for RIO-MJP (PostgreSQL, Backend, Frontend).
Automatically ensures PostgreSQL is listening on port 5433, then starts Backend and Frontend.
Press Ctrl+C to cleanly stop all services.
"""

import os
import sys
import time
import socket
import subprocess

def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0

def ensure_postgres(root_dir: str):
    if is_port_in_use(5433):
        print("[1/3] PostgreSQL: Already running on port 5433.")
        return None

    print("[1/3] PostgreSQL: Starting cluster on port 5433...")
    pg_data = os.path.join(root_dir, "test_pg_5433")
    pg_ctl = r"C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe"
    pg_exe = r"C:\Program Files\PostgreSQL\18\bin\postgres.exe"

    if os.path.exists(pg_ctl) and os.path.exists(pg_data):
        log_file = os.path.join(pg_data, "postgres.log")
        subprocess.run([pg_ctl, "start", "-D", pg_data, "-l", log_file], capture_output=True)
    elif os.path.exists(pg_exe) and os.path.exists(pg_data):
        proc = subprocess.Popen([pg_exe, "-D", pg_data], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return proc

    for _ in range(20):
        if is_port_in_use(5433):
            print("      PostgreSQL is ready to accept connections.")
            return None
        time.sleep(0.5)

    print("Warning: PostgreSQL port 5433 did not open within 10s.")
    return None

def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    frontend_dir = os.path.join(root_dir, "frontend")

    # Path to virtual environment python
    venv_py = os.path.join(root_dir, "venv", "Scripts", "python.exe")
    py_exec = venv_py if os.path.exists(venv_py) else sys.executable

    print("\n" + "=" * 55)
    print("      Starting RIO-MJP (Database + Backend + Frontend) ")
    print("  • Database: 127.0.0.1:5433                          ")
    print("  • Backend:  http://127.0.0.1:8000                   ")
    print("  • Frontend: http://localhost:5173                   ")
    print("  • Docs:     http://127.0.0.1:8000/docs              ")
    print("=" * 55)
    print("Press Ctrl+C at any time to stop services.\n")

    # 1. Ensure PostgreSQL is up
    pg_proc = ensure_postgres(root_dir)

    # 2. Start FastAPI backend process
    print("[2/3] Backend: Starting FastAPI on port 8000...")
    backend_proc = subprocess.Popen(
        [py_exec, "-m", "uvicorn", "backend.main:app", "--reload", "--host", "127.0.0.1", "--port", "8000"],
        cwd=root_dir
    )

    # 3. Start React Vite frontend process
    print("[3/3] Frontend: Starting Vite on port 5173...")
    frontend_proc = subprocess.Popen(
        "npm run dev",
        cwd=frontend_dir,
        shell=True
    )

    print("\n✓ All RIO-MJP services are running!\n")

    try:
        while True:
            time.sleep(1)
            if backend_proc.poll() is not None or frontend_proc.poll() is not None:
                break
    except KeyboardInterrupt:
        print("\n[Ctrl+C received] Shutting down RIO-MJP services...")
    finally:
        for proc in (backend_proc, frontend_proc, pg_proc):
            if proc:
                try:
                    proc.terminate()
                except Exception:
                    pass

        try:
            if frontend_proc.pid:
                subprocess.run(f"taskkill /F /T /PID {frontend_proc.pid}", shell=True, capture_output=True)
            if backend_proc.pid:
                subprocess.run(f"taskkill /F /T /PID {backend_proc.pid}", shell=True, capture_output=True)
        except Exception:
            pass

        print("All RIO-MJP services have been stopped safely.\n")

if __name__ == "__main__":
    main()
