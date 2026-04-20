# package.ps1 — Build a portable Slimarr deployment ZIP
# Run: .\package.ps1
# Output: slimarr-portable.zip (ready to copy to server)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$OutDir  = "$Root\dist\slimarr"
$ZipFile = "$Root\slimarr-portable.zip"

Write-Host ""
Write-Host "  Packaging Slimarr for deployment..." -ForegroundColor Cyan
Write-Host ""

# ── Clean ─────────────────────────────────────────────────────────────────────
if (Test-Path "$Root\dist") { Remove-Item "$Root\dist" -Recurse -Force }
if (Test-Path $ZipFile) { Remove-Item $ZipFile -Force }

New-Item -ItemType Directory -Path $OutDir | Out-Null

# ── Build frontend if needed ──────────────────────────────────────────────────
if (-not (Test-Path "$Root\frontend\dist\index.html")) {
    Write-Host "  Building frontend..." -ForegroundColor Yellow
    Push-Location "$Root\frontend"
    npm install --silent
    npm run build
    Pop-Location
}

# ── Copy application files ────────────────────────────────────────────────────
$dirs = @(
    "backend",
    "frontend\dist",
    "images",
    "docs"
)
foreach ($d in $dirs) {
    $src = Join-Path $Root $d
    $dst = Join-Path $OutDir $d
    if (Test-Path $src) {
        Copy-Item $src $dst -Recurse -Force
        # Remove __pycache__
        Get-ChildItem $dst -Directory -Recurse -Filter "__pycache__" | Remove-Item -Recurse -Force
    }
}

# Copy root files
$files = @(
    "requirements.txt",
    "run.py",
    "tray.py",
    "install.ps1",
    "install.sh",
    "README.md",
    "LICENSE",
    ".gitignore"
)
foreach ($f in $files) {
    $src = Join-Path $Root $f
    if (Test-Path $src) { Copy-Item $src $OutDir }
}

# ── Create update script ─────────────────────────────────────────────────────
@"
@echo off
setlocal
cd /d "%~dp0"

echo.
echo   Slimarr Updater
echo   ================
echo.
echo   Downloading latest version from GitHub...
echo.

REM Download latest zip from GitHub
powershell -Command "Invoke-WebRequest -Uri 'https://github.com/theantipopau/slimarr/archive/refs/heads/main.zip' -OutFile update-tmp.zip"
if errorlevel 1 (
    echo   ERROR: Download failed. Check your internet connection.
    pause
    exit /b 1
)

REM Extract to temp folder
if exist update-tmp rmdir /s /q update-tmp
powershell -Command "Expand-Archive -Path update-tmp.zip -DestinationPath update-tmp -Force"

REM Copy code files (preserves config.yaml, data/, venv/)
set SRC=update-tmp\slimarr-main

echo   Updating backend...
if exist backend rmdir /s /q backend
xcopy "%SRC%\backend" "backend\" /E /I /Q /Y >nul

echo   Updating frontend...
if exist "%SRC%\frontend\dist" (
    if exist "frontend\dist" rmdir /s /q "frontend\dist"
    xcopy "%SRC%\frontend\dist" "frontend\dist\" /E /I /Q /Y >nul
) else (
    echo   NOTE: No pre-built frontend in repo. Keeping current version.
)

echo   Updating root files...
for %%F in (requirements.txt run.py tray.py install.ps1 install.sh README.md LICENSE) do (
    if exist "%SRC%\%%F" copy /Y "%SRC%\%%F" "%%F" >nul
)

REM Cleanup
del update-tmp.zip >nul 2>&1
rmdir /s /q update-tmp >nul 2>&1

echo   Reinstalling dependencies...
venv\Scripts\python.exe -m pip install -q -r requirements.txt 2>>startup-error.log
if errorlevel 1 (
    echo   WARNING: Dependency install had errors. Check startup-error.log
)

echo.
echo   Update complete! Run start.bat to launch.
echo.
pause
"@ | Set-Content "$OutDir\update.bat" -Encoding ASCII

# ── Create data dirs ─────────────────────────────────────────────────────────
foreach ($d in @("data", "data\logs", "data\MediaCover", "data\recycling")) {
    New-Item -ItemType Directory -Path "$OutDir\$d" -Force | Out-Null
}

# ── Create default config ────────────────────────────────────────────────────
@"
# Slimarr Configuration — Edit these values for your server
server:
  host: "0.0.0.0"
  port: 9494
  log_level: "info"

plex:
  url: "http://localhost:32400"
  token: ""
  library_sections: []

sabnzbd:
  url: "http://localhost:8080"
  api_key: ""
  category: "slimarr"

indexers: []
# Add your Newznab indexers here, or use the Settings page after first run:
# - name: "NZBgeek"
#   url: "https://api.nzbgeek.info"
#   api_key: "your-key-here"
#   categories: [2000, 2010, 2020, 2030, 2040, 2045, 2050, 2060]

prowlarr:
  enabled: false
  url: ""
  api_key: ""

radarr:
  enabled: false
  url: "http://localhost:7878"
  api_key: ""

tmdb:
  api_key: ""

comparison:
  min_savings_percent: 10.0
  allow_resolution_downgrade: false
  downgrade_min_savings_percent: 40.0
  preferred_codecs: ["av1", "h265"]
  max_candidate_age_days: 3650
  minimum_file_size_mb: 500

files:
  recycling_bin: "./data/recycling"
  recycling_bin_cleanup_days: 30

schedule:
  start_time: "01:00"
  end_time: "07:00"
  max_downloads_per_night: 10
  throttle_seconds: 30
"@ | Set-Content "$OutDir\config.yaml" -Encoding UTF8

# ── Create quick-start script ────────────────────────────────────────────────
@"
@echo off
setlocal
cd /d "%~dp0"

echo.
echo   Slimarr Quick Start
echo   ====================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo   ERROR: Python 3.12+ not found.
    echo   Download from: https://www.python.org/downloads/
    echo   Tick "Add Python to PATH" during install.
    pause
    exit /b 1
)

REM Remove broken venv if pip is missing inside it
if exist venv (
    venv\Scripts\python.exe -m pip --version >nul 2>&1
    if errorlevel 1 (
        echo   Removing broken virtual environment...
        rmdir /s /q venv
    )
)

REM Create venv if needed
if not exist venv (
    echo   Creating virtual environment...
    python -m venv venv --without-pip
    if errorlevel 1 (
        echo   ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
)

REM Bootstrap pip if missing (handles broken ensurepip on some Windows installs)
venv\Scripts\python.exe -m pip --version >nul 2>&1
if errorlevel 1 (
    echo   Bootstrapping pip...
    venv\Scripts\python.exe -m ensurepip --upgrade >>startup-error.log 2>&1
    if errorlevel 1 (
        echo   Downloading pip installer...
        powershell -Command "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile get-pip.py"
        venv\Scripts\python.exe get-pip.py >>startup-error.log 2>&1
        del get-pip.py >nul 2>&1
    )
)

REM Install dependencies
echo   Installing Python dependencies (first run may take a minute)...
venv\Scripts\python.exe -m pip install --upgrade pip >>startup-error.log 2>&1
venv\Scripts\python.exe -m pip install -r requirements.txt >>startup-error.log 2>&1
if errorlevel 1 (
    echo   ERROR: Dependency install failed. Details:
    echo.
    type startup-error.log
    echo.
    pause
    exit /b 1
)

REM Start server
echo.
echo   Starting Slimarr on http://localhost:9494
echo   Open your browser to http://localhost:9494 to get started.
echo   Press Ctrl+C to stop.
echo.
venv\Scripts\python.exe run.py --headless 2>>startup-error.log
if errorlevel 1 (
    echo.
    echo   ERROR: Slimarr crashed. Check startup-error.log and data\logs\slimarr.log
    pause
)
"@ | Set-Content "$OutDir\start.bat" -Encoding ASCII

@"
#!/bin/bash
cd "`$(dirname "`$0")"
echo ""
echo "  Slimarr Quick Start"
echo "  ===================="
echo ""

PYTHON=`$(command -v python3.12 2>/dev/null || command -v python3.13 2>/dev/null || command -v python3.11 2>/dev/null || command -v python3 2>/dev/null)
if [ -z "`$PYTHON" ]; then echo "ERROR: Python 3.11+ not found."; exit 1; fi

if [ ! -d venv ]; then
    echo "  Creating virtual environment..."
    "`$PYTHON" -m venv venv
fi

echo "  Installing Python dependencies..."
venv/bin/python -m pip install -q --upgrade pip 2>>startup-error.log
venv/bin/python -m pip install -q -r requirements.txt 2>>startup-error.log

echo ""
echo "  Starting Slimarr on http://localhost:9494"
echo "  Press Ctrl+C to stop."
echo ""
venv/bin/python run.py --headless 2>>startup-error.log || {
    echo ""
    echo "  ERROR: Slimarr crashed. Check startup-error.log and data/logs/slimarr.log"
    exit 1
}
"@ | Set-Content "$OutDir\start.sh" -Encoding UTF8

# ── Zip it ────────────────────────────────────────────────────────────────────
Write-Host "  Compressing..." -ForegroundColor Cyan
Compress-Archive -Path $OutDir -DestinationPath $ZipFile -Force

$size = [math]::Round((Get-Item $ZipFile).Length / 1MB, 1)
Write-Host ""
Write-Host "  Done! Package created: slimarr-portable.zip (${size} MB)" -ForegroundColor Green
Write-Host ""
Write-Host "  To deploy on your server:" -ForegroundColor White
Write-Host "    1. Copy slimarr-portable.zip to the server" -ForegroundColor Gray
Write-Host "    2. Unzip into any directory" -ForegroundColor Gray
Write-Host "    3. Edit config.yaml (Plex token, SABnzbd key, indexers)" -ForegroundColor Gray
Write-Host "    4. Run: start.bat (Windows) or bash start.sh (Linux)" -ForegroundColor Gray
Write-Host "    5. Open http://server-ip:9494 and register" -ForegroundColor Gray
Write-Host ""

# Clean up intermediate
Remove-Item -Path "$Root\dist" -Recurse -Force
