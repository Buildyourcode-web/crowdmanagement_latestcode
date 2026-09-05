@echo off
title BYC AI - FastAPI Backend (Port 8000)
cd /d "%~dp0"
echo ========================================================
echo Starting BYC AI Backend on http://localhost:8000 ...
echo ========================================================
venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8000 --reload --app-dir backend
pause
