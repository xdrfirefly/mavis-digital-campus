@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Mavis Digital Campus - Import Previous Data

echo ======================================================
echo      MAVIS DIGITAL CAMPUS - IMPORT PREVIOUS DATA
echo ======================================================
echo.
echo This copies ONLY your local Campus data into this new version:
echo   - mavis.db
echo   - .env (if present)
echo   - repository folder
echo   - library folder
echo.
echo New app code in this folder will NOT be replaced.
echo.

set "OLD=%~1"
if not defined OLD (
  echo TIP: You can also drag the OLD Campus folder onto this BAT file.
  echo.
  set /p "OLD=Paste the full path to your previous Campus folder: "
)
set "OLD=%OLD:"=%"
if not defined OLD goto :failed

set "PY_EXE="
where py >nul 2>&1 && set "PY_EXE=py"
if not defined PY_EXE where python >nul 2>&1 && set "PY_EXE=python"
if not defined PY_EXE where python3 >nul 2>&1 && set "PY_EXE=python3"
if not defined PY_EXE (
  echo [ERROR] Python could not be found.
  goto :failed
)

%PY_EXE% upgrade_helper.py import-folder "%OLD%"
if errorlevel 1 goto :failed

echo.
echo [DONE] Your previous Campus data is now in this version.
echo Start run_windows.bat normally.
pause
exit /b 0

:failed
echo.
echo [FAILED] Nothing else was changed after the reported error.
pause
exit /b 1
