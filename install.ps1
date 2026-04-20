# install.ps1 -- Slimarr installation script for Windows
# Run from C:\Slimarr with: .\install.ps1
# Options:
#   -SkipFrontend     Skip npm install + build (use if frontend already built)
#   -InstallService   Install as a Windows service (auto-starts on boot)
#   -Uninstall        Remove the Windows service

param(
    [switch]$SkipFrontend,
    [switch]$InstallService,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$ServiceName = "Slimarr"

# ── Uninstall ─────────────────────────────────────────────────────────────────
if ($Uninstall) {
    Write-Host "  Removing Slimarr service..." -ForegroundColor Yellow
    if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
        sc.exe delete $ServiceName | Out-Null
        Write-Host "  Service removed." -ForegroundColor Green
    } else {
        Write-Host "  Service not found." -ForegroundColor Gray
    }
    exit 0
}

Write-Host ""
Write-Host "  ┌─────────────────────────────┐" -ForegroundColor Green
Write-Host "  │   Slimarr Installer v1.0    │" -ForegroundColor Green
Write-Host "  └─────────────────────────────┘" -ForegroundColor Green
Write-Host ""

# ── 1. Python venv ────────────────────────────────────────────────────────────
Write-Host "[1/5] Setting up Python virtual environment..." -ForegroundColor Cyan

# Find Python executable
$pythons = @(
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
    "python3",
    "python"
)
$pyExe = $null
foreach ($p in $pythons) {
    if (Test-Path $p) { $pyExe = $p; break }
    try { if (Get-Command $p -ErrorAction Stop) { $pyExe = $p; break } } catch {}
}
if (-not $pyExe) {
    Write-Error "Python 3.12+ not found. Install from https://python.org and re-run."
    exit 1
}
Write-Host "  Using: $pyExe" -ForegroundColor Gray

# Remove broken venv if pip is missing inside it
if (Test-Path "$Root\venv") {
    $pipCheck = & "$Root\venv\Scripts\python.exe" -m pip --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  Removing broken virtual environment..." -ForegroundColor Yellow
        Remove-Item -Recurse -Force "$Root\venv"
    }
}

# Create venv if needed
if (-not (Test-Path "$Root\venv")) {
    Write-Host "  Creating virtual environment..." -ForegroundColor Gray
    & $pyExe -m venv "$Root\venv" --without-pip
}

# Bootstrap pip if missing
$pipCheck = & "$Root\venv\Scripts\python.exe" -m pip --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Bootstrapping pip..." -ForegroundColor Gray
    & "$Root\venv\Scripts\python.exe" -m ensurepip --upgrade 2>&1 | Out-Null
    $pipCheck = & "$Root\venv\Scripts\python.exe" -m pip --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  Downloading pip installer..." -ForegroundColor Gray
        Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile "$Root\get-pip.py"
        & "$Root\venv\Scripts\python.exe" "$Root\get-pip.py"
        Remove-Item "$Root\get-pip.py" -ErrorAction SilentlyContinue
    }
}

Write-Host "  Virtual environment ready." -ForegroundColor Green

# ── 2. pip install ────────────────────────────────────────────────────────────
Write-Host "[2/5] Installing Python dependencies..." -ForegroundColor Cyan
& "$Root\venv\Scripts\python.exe" -m pip install --upgrade pip -q
& "$Root\venv\Scripts\python.exe" -m pip install -r "$Root\requirements.txt" -q
if ($LASTEXITCODE -ne 0) {
    Write-Error "Dependency install failed. Check the output above."
    exit 1
}
Write-Host "  Python dependencies installed." -ForegroundColor Green

# ── 3. Frontend ───────────────────────────────────────────────────────────────
if (-not $SkipFrontend) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Write-Error "npm not found. Install Node.js 18+ from https://nodejs.org"
        exit 1
    }
    Write-Host "[3/5] Installing frontend dependencies..." -ForegroundColor Cyan
    Push-Location "$Root\frontend"
    npm install --silent
    Write-Host "[4/5] Building frontend..." -ForegroundColor Cyan
    npm run build
    Pop-Location
    Write-Host "  Frontend built." -ForegroundColor Green
} else {
    Write-Host "[3/5] Skipping frontend (--SkipFrontend)." -ForegroundColor Yellow
    Write-Host "[4/5] Skipping frontend build." -ForegroundColor Yellow
}

# ── 4. Data directories + default config ─────────────────────────────────────
Write-Host "[5/5] Preparing data directories..." -ForegroundColor Cyan
$dirs = @("$Root\data", "$Root\data\logs", "$Root\data\MediaCover", "$Root\data\recycling")
foreach ($d in $dirs) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d | Out-Null }
}

if (-not (Test-Path "$Root\config.yaml")) {
    @"
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

prowlarr:
  enabled: false
  url: "http://localhost:9696"
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
"@ | Set-Content "$Root\config.yaml" -Encoding UTF8
    Write-Host "  Created default config.yaml — edit it before starting!" -ForegroundColor Yellow
}
Write-Host "  Data directories ready." -ForegroundColor Green

# ── 5. Optional Windows service ───────────────────────────────────────────────
if ($InstallService) {
    Write-Host "Installing Windows service..." -ForegroundColor Cyan
    $pyExe   = "$Root\venv\Scripts\python.exe"
    $runPy   = "$Root\run.py"
    $binPath = "`"$pyExe`" `"$runPy`" --headless"

    if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
        sc.exe delete $ServiceName | Out-Null
        Start-Sleep -Seconds 1
    }
    sc.exe create $ServiceName binpath= $binPath start= auto obj= LocalSystem DisplayName= "Slimarr" | Out-Null
    sc.exe description $ServiceName "Slimarr — Smart Plex movie replacement manager" | Out-Null
    sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/10000/restart/30000 | Out-Null
    Start-Service -Name $ServiceName
    Write-Host "  Service '$ServiceName' installed and started." -ForegroundColor Green
    Write-Host "  Manage with: Start-Service $ServiceName / Stop-Service $ServiceName" -ForegroundColor Gray
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ✓ Installation complete!" -ForegroundColor Green
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor White
Write-Host "    1. Edit config.yaml with your Plex token, SABnzbd API key, etc." -ForegroundColor Gray
Write-Host "    2. Start Slimarr:" -ForegroundColor Gray
Write-Host "         python run.py                    # tray app" -ForegroundColor DarkGray
Write-Host "         python run.py --headless         # no tray" -ForegroundColor DarkGray
Write-Host "         .\install.ps1 -InstallService    # Windows service (auto-start)" -ForegroundColor DarkGray
Write-Host "    3. Open http://localhost:9494 and register your account." -ForegroundColor Gray
Write-Host ""


$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host ""
Write-Host "  Slimarr Installer" -ForegroundColor Green
Write-Host "  ==================" -ForegroundColor DarkGreen
Write-Host ""

# 1. Python venv
Write-Host "[1/5] Setting up Python virtual environment..." -ForegroundColor Cyan
if (-not (Test-Path "$Root\venv")) {
    $pythons = @(
        "C:\Users\$env:USERNAME\AppData\Local\Programs\Python\Python312\python.exe",
        "python3",
        "python"
    )
    $pyExe = $null
    foreach ($p in $pythons) {
        if (Get-Command $p -ErrorAction SilentlyContinue) { $pyExe = $p; break }
        if (Test-Path $p) { $pyExe = $p; break }
    }
    if (-not $pyExe) {
        Write-Error "Python 3.12+ not found. Install from https://python.org"
        exit 1
    }
    & $pyExe -m venv venv
}
Write-Host "  Virtual environment ready." -ForegroundColor Green

# 2. pip install
Write-Host "[2/5] Installing Python dependencies..." -ForegroundColor Cyan
& "$Root\venv\Scripts\python.exe" -m pip install --upgrade pip -q
& "$Root\venv\Scripts\python.exe" -m pip install -r "$Root\requirements.txt" -q
Write-Host "  Python dependencies installed." -ForegroundColor Green

# 3. Frontend
if (-not $SkipFrontend) {
    Write-Host "[3/5] Installing frontend dependencies..." -ForegroundColor Cyan
    Push-Location "$Root\frontend"
    npm install
    Write-Host "[4/5] Building frontend..." -ForegroundColor Cyan
    npm run build
    Pop-Location
    Write-Host "  Frontend built." -ForegroundColor Green
} else {
    Write-Host "[3/5] Skipping frontend (--SkipFrontend)." -ForegroundColor Yellow
    Write-Host "[4/5] Skipping frontend build." -ForegroundColor Yellow
}

# 4. Copy logo to public
Write-Host "[5/5] Copying brand assets..." -ForegroundColor Cyan
$publicDir = "$Root\frontend\public"
if (-not (Test-Path $publicDir)) { New-Item -ItemType Directory -Path $publicDir | Out-Null }

if (Test-Path "$Root\images\header-logo.PNG") {
    Copy-Item "$Root\images\header-logo.PNG" "$publicDir\logo.png" -Force
    Write-Host "  Copied logo.png" -ForegroundColor Green
}

# 5. Optional Windows service
if ($InstallService) {
    Write-Host "Installing Windows service..." -ForegroundColor Cyan
    $serviceName = "Slimarr"
    $binPath = "`"$Root\venv\Scripts\python.exe`" `"$Root\run.py`" --headless"
    if (Get-Service -Name $serviceName -ErrorAction SilentlyContinue) {
        Stop-Service -Name $serviceName -Force -ErrorAction SilentlyContinue
        sc.exe delete $serviceName | Out-Null
    }
    sc.exe create $serviceName binpath= $binPath start= auto DisplayName= "Slimarr" | Out-Null
    sc.exe description $serviceName "Slimarr -- Smart Plex movie replacement manager" | Out-Null
    Start-Service -Name $serviceName
    Write-Host "  Service installed and started." -ForegroundColor Green
}

Write-Host ""
Write-Host "  Installation complete!" -ForegroundColor Green
Write-Host "  To start: .\venv\Scripts\python.exe run.py" -ForegroundColor White
    Write-Host "  Web UI will open at http://localhost:9494" -ForegroundColor Cyan
Write-Host ""
