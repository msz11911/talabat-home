@echo off
cd /d "%~dp0"
if not exist ".venv" (
  python -m venv .venv
)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
".venv\Scripts\python.exe" -m uvicorn app:app --host 0.0.0.0 --port 8000
pause
