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

echo Waiting for Slimarr to start (up to 60 seconds)...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$deadline=(Get-Date).AddSeconds(60);" ^
  "while ((Get-Date) -lt $deadline) {" ^
  "  try {" ^
  "    $r=Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:9494/api/v1/system/health' -TimeoutSec 2;" ^
  "    if ($r.StatusCode -ge 200) { Start-Process 'http://localhost:9494'; exit 0 }" ^
  "  } catch {}" ^
  "  Start-Sleep -Milliseconds 500" ^
  "};" ^
  "Start-Process 'http://localhost:9494'"
exit /b 0
