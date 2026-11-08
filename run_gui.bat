@echo off
REM Starts the legacy Tkinter bulk upload tool
cd /d "%~dp0"
echo Starting Bulk Upload GUI...
venv\Scripts\python.exe app\bulk_upload_gui.py
pause
