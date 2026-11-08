@echo off
REM Starts the CrawlFlow control panel (API + web UI) at http://127.0.0.1:8765
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
  echo Virtual environment missing. Run: python -m venv venv ^&^& venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)
echo Starting CrawlFlow control panel...
echo Open http://127.0.0.1:8765 in your browser once loaded.
venv\Scripts\python.exe -m uvicorn app.web_api:app --host 127.0.0.1 --port 8765
