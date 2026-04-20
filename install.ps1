# install.ps1 -- Slimarr installation script
# Run from C:\Slimarr with: .\install.ps1
param(
    [switch]$SkipFrontend,
    [switch]$InstallService
)

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
& "$Root\venv\Scripts\pip" install --upgrade pip -q
& "$Root\venv\Scripts\pip" install -r "$Root\requirements.txt"
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
