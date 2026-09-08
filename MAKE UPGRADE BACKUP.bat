@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Mavis Digital Campus - Upgrade Backup

echo ======================================================
echo        MAVIS DIGITAL CAMPUS - UPGRADE BACKUP
echo ======================================================
echo.
echo This creates one ZIP containing mavis.db, repository, and library.
echo For safety, .env/API keys are NOT included.
echo.

set "PY_EXE="
where py >nul 2>&1 && set "PY_EXE=py"
if not defined PY_EXE where python >nul 2>&1 && set "PY_EXE=python"
if not defined PY_EXE where python3 >nul 2>&1 && set "PY_EXE=python3"
if not defined PY_EXE (
  echo [ERROR] Python could not be found.
  pause
  exit /b 1
)

%PY_EXE% upgrade_helper.py backup
if errorlevel 1 (
  echo.
  echo [FAILED] Backup was not created.
  pause
  exit /b 1
)

echo.
echo [DONE] Look in the upgrade_backups folder.
pause
