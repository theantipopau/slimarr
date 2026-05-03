@echo off
setlocal

cd /d "%~dp0"
set "PY=%CD%\venv\Scripts\python.exe"

if not exist "%PY%" (
  echo.
  echo [ERROR] Slimarr is not installed yet (missing venv\Scripts\python.exe).
  echo Run install.ps1 first, then run this script again.
  echo.
  pause
  exit /b 1
)

echo Starting Slimarr...
start "Slimarr" "%PY%" "run.py" --headless
start "" "http://localhost:9494"
echo Browser opened at http://localhost:9494
