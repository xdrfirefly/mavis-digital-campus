@echo off
setlocal
cd /d "%~dp0"
title Mavis Digital Campus Diagnostics v0.4

echo ===============================================
echo       MAVIS DIGITAL CAMPUS DIAGNOSTICS
echo ===============================================
echo.

echo --- Microsoft Store command: python3 ---
where python3 2>&1
python3 --version 2>&1

echo.
echo --- Python.org launcher: py ---
where py 2>&1
py --version 2>&1

echo.
echo --- Generic Python command: python ---
where python 2>&1
python --version 2>&1

echo.
echo --- Windows App Execution Alias folder ---
echo %LOCALAPPDATA%\Microsoft\WindowsApps
dir "%LOCALAPPDATA%\Microsoft\WindowsApps\python*.exe" 2>&1

echo.
echo --- Virtual environment ---
if exist ".venv\Scripts\python.exe" (
  echo Found .venv\Scripts\python.exe
  ".venv\Scripts\python.exe" --version
  ".venv\Scripts\python.exe" -m pip show fastapi uvicorn
) else (
  echo No virtual environment has been created yet.
)

echo.
echo --- Port 8000 ---
netstat -ano | findstr ":8000"
if errorlevel 1 echo Nothing is currently listening on port 8000.

echo.
echo --- Files ---
if exist app.py (echo app.py: OK) else (echo app.py: MISSING)
if exist requirements.txt (echo requirements.txt: OK) else (echo requirements.txt: MISSING)
if exist static\index.html (echo static\index.html: OK) else (echo static\index.html: MISSING)

echo.
echo If python3 works above but startup still fails, send me a screenshot of this window.
pause
