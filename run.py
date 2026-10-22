"""
run.py — One-command runner to run Backend and Frontend concurrently in one terminal.
Press Ctrl+C to cleanly stop both services.
"""

import os
import sys
import subprocess
import time

def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    frontend_dir = os.path.join(root_dir, "frontend")

    # Path to virtual environment python
    venv_py = os.path.join(root_dir, "venv", "Scripts", "python.exe")
    py_exec = venv_py if os.path.exists(venv_py) else sys.executable

    print("\n" + "=" * 55)
    print("      Starting RIO-MJP (Backend + Frontend)        ")
    print("  • Backend:  http://127.0.0.1:8000                ")
    print("  • Frontend: http://localhost:5173                ")
    print("  • Docs:     http://127.0.0.1:8000/docs           ")
    print("=" * 55)
    print("Press Ctrl+C at any time to stop both.\n")

    # Start FastAPI backend process
    backend_proc = subprocess.Popen(
        [py_exec, "-m", "uvicorn", "backend.main:app", "--reload", "--host", "127.0.0.1", "--port", "8000"],
        cwd=root_dir
    )

    # Start React Vite frontend process
    frontend_proc = subprocess.Popen(
        "npm run dev",
        cwd=frontend_dir,
        shell=True
    )

    try:
        while True:
            time.sleep(1)
            # If any process exits unexpectedly, terminate the other
            if backend_proc.poll() is not None or frontend_proc.poll() is not None:
                break
    except KeyboardInterrupt:
        print("\n[Ctrl+C received] Shutting down RIO-MJP services...")
    finally:
        # Gracefully terminate child processes
        for proc in (backend_proc, frontend_proc):
            try:
                proc.terminate()
            except Exception:
                pass

        # Windows taskkill fallback for shell child processes
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
