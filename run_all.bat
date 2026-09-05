@echo off
title BYC AI Command Center - Launcher
cd /d "%~dp0"
echo ========================================================
echo Launching BYC AI Command Center (Backend + Frontend)
echo ========================================================
start "BYC AI Backend" cmd /k "run_backend.bat"
timeout /t 3 /nobreak >nul
start "BYC AI Frontend" cmd /k "run_frontend.bat"
echo.
echo Both Backend (http://localhost:8000) and Frontend (http://localhost:5173) are starting!
echo.
pause
