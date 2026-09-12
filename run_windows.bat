@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Mavis Digital Campus v0.8.7.3.2

echo ===============================================
echo       MAVIS DIGITAL CAMPUS v0.8.7.3.2
echo ===============================================
echo.

set "PY_EXE="
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" --version >nul 2>&1
  if not errorlevel 1 set "PY_EXE=.venv\Scripts\python.exe"
)
if not defined PY_EXE (
  where python3 >nul 2>&1
  if %errorlevel%==0 (
    python3 --version >nul 2>&1
    if %errorlevel%==0 set "PY_EXE=python3"
  )
)
if not defined PY_EXE (
  where py >nul 2>&1
  if %errorlevel%==0 (
    py --version >nul 2>&1
    if %errorlevel%==0 set "PY_EXE=py"
  )
)
if not defined PY_EXE (
  where python >nul 2>&1
  if %errorlevel%==0 (
    python --version >nul 2>&1
    if %errorlevel%==0 set "PY_EXE=python"
  )
)
if not defined PY_EXE (
  if exist "%LOCALAPPDATA%\Microsoft\WindowsApps\python3.exe" set "PY_EXE=%LOCALAPPDATA%\Microsoft\WindowsApps\python3.exe"
)
if not defined PY_EXE (
  if exist "%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe" set "PY_EXE=%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe"
)
if not defined PY_EXE (
  echo [ERROR] Python could not be launched.
  echo Run diagnose_windows.bat and send me a screenshot.
  pause
  exit /b 1
)

echo [1/5] Python found:
"%PY_EXE%" --version
if errorlevel 1 goto :failed

echo.
echo [2/5] Preparing local environment...
if not exist ".venv\Scripts\python.exe" (
  "%PY_EXE%" -m venv .venv
  if errorlevel 1 goto :failed
)

echo.
echo [3/5] Installing/checking required packages...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :failed

rem Find the first free local port, beginning with 8000.
set "PORT="
for /f %%P in ('powershell -NoProfile -Command "$ports=8000..8010; foreach($p in $ports){ if(-not (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)){ Write-Output $p; break } }"') do if not defined PORT set "PORT=%%P"
if not defined PORT set "PORT=8042"

echo.
echo [4/5] Local address: http://127.0.0.1:!PORT!/
if not "!PORT!"=="8000" echo [INFO] Port 8000 is already in use, probably by an older campus window. v0.8.7.3.2 will use !PORT! instead.
echo The browser will open only after THIS version is ready.
echo Keep this window OPEN while you use the campus.
echo.

start "" powershell -NoProfile -WindowStyle Hidden -Command "$url='http://127.0.0.1:!PORT!/?v=08732'; for($i=0;$i -lt 80;$i++){ try { $r=Invoke-WebRequest -UseBasicParsing $url -TimeoutSec 1; if($r.StatusCode -ge 200){ Start-Process $url; exit 0 } } catch {}; Start-Sleep -Milliseconds 400 }"

echo [5/5] Server log:
".venv\Scripts\python.exe" -m uvicorn app:app --host 127.0.0.1 --port !PORT! --log-level info
set "SERVER_EXIT=!errorlevel!"

echo.
echo The Mavis server stopped with exit code !SERVER_EXIT!.
echo If you did not close it intentionally, photograph the error above.
pause
exit /b !SERVER_EXIT!

:failed
echo.
echo ===============================================
echo STARTUP FAILED
echo ===============================================
echo Please photograph or copy the error above and send it to me.
pause
exit /b 1
