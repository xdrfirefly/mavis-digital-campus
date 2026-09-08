@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Mavis Digital Campus - Restore Upgrade Backup

echo ======================================================
echo       MAVIS DIGITAL CAMPUS - RESTORE BACKUP
echo ======================================================
echo.
echo Restore a Mavis-Campus-Data-Backup ZIP into this version.
echo A safety backup of any existing data here is made first.
echo.

set "BACKUP=%~1"
if not defined BACKUP (
  echo TIP: You can drag the backup ZIP onto this BAT file.
  echo.
  set /p "BACKUP=Paste the full path to the backup ZIP: "
)
set "BACKUP=%BACKUP:"=%"
if not defined BACKUP goto :failed

set "PY_EXE="
where py >nul 2>&1 && set "PY_EXE=py"
if not defined PY_EXE where python >nul 2>&1 && set "PY_EXE=python"
if not defined PY_EXE where python3 >nul 2>&1 && set "PY_EXE=python3"
if not defined PY_EXE goto :failed

%PY_EXE% upgrade_helper.py restore "%BACKUP%"
if errorlevel 1 goto :failed

echo.
echo [DONE] Backup restored. Copy your .env separately if this is a fresh folder.
pause
exit /b 0

:failed
echo.
echo [FAILED] Restore did not complete.
pause
exit /b 1
