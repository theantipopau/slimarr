# build-installer.ps1 - Build the Slimarr Windows installer
# Output: dist/installer/SlimarrSetup-1.0.0.4.exe
#
# Prerequisites (install once):
#   pip install pyinstaller          (in your venv)
#   winget install JRSoftware.InnoSetup   (or https://jrsoftware.org/isdl.php)
#
# Usage:
#   .\build-installer.ps1
#   .\build-installer.ps1 -SkipFrontend    # skip npm build if already built
#   .\build-installer.ps1 -SkipPyInstaller # skip PyInstaller if already built

param(
    [switch]$SkipFrontend,
    [switch]$SkipPyInstaller
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Write-Step($n, $msg) {
    Write-Host ""
    Write-Host "  [$n] $msg" -ForegroundColor Cyan
}
function Write-Ok($msg)  { Write-Host "      OK: $msg" -ForegroundColor Green }
function Write-Err($msg) { Write-Host "      ERROR: $msg" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "  +-------------------------------------+" -ForegroundColor Green
Write-Host "  |   Slimarr Installer Builder v1.0   |" -ForegroundColor Green
Write-Host "  +-------------------------------------+" -ForegroundColor Green

# ---- 0. Sanity checks -------------------------------------------------------
Write-Step "0" "Checking prerequisites"

$Python = "$Root\venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { Write-Err "venv not found. Run install.ps1 first." }
Write-Ok "Python venv: $Python"

$PyInstaller = "$Root\venv\Scripts\pyinstaller.exe"
if (-not (Test-Path $PyInstaller)) {
    Write-Host "      Installing PyInstaller..." -ForegroundColor Yellow
    & "$Root\venv\Scripts\pip.exe" install pyinstaller --quiet
}
Write-Ok "PyInstaller: found"

$ISSPaths = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
    "ISCC.exe"
)
$ISCC = $null
foreach ($p in $ISSPaths) {
    try { if (Test-Path $p -ErrorAction Stop) { $ISCC = $p; break } } catch {}
    try { if (Get-Command $p -ErrorAction Stop) { $ISCC = $p; break } } catch {}
}
if (-not $ISCC) {
    Write-Err "Inno Setup 6 not found. Install from: https://jrsoftware.org/isdl.php or run: winget install JRSoftware.InnoSetup"
}
Write-Ok "Inno Setup: $ISCC"

# ---- 1. Convert icon PNG -> ICO --------------------------------------------
Write-Step "1" "Creating Windows icon (icon.ico)"
& $Python "$Root\scripts\build_icon.py" "$Root"
if ($LASTEXITCODE -ne 0) { Write-Err "Icon conversion failed" }
Write-Ok "images/icon.ico created"

# ---- 2. Create config.yaml.example -----------------------------------------
Write-Step "2" "Writing config.yaml.example"
$cfgLines = @(
    '# Slimarr configuration - edit these settings via the web UI at http://localhost:9494',
    'server:',
    '  port: 9494',
    '',
    'auth:',
    '  secret_key: ""',
    '',
    'plex:',
    '  url: ""',
    '  token: ""',
    '',
    'download_client: "sabnzbd"',
    '',
    'sabnzbd:',
    '  url: ""',
    '  api_key: ""',
    '  category: "slimarr"',
    '',
    'nzbget:',
    '  url: ""',
    '  username: ""',
    '  password: ""',
    '  category: "slimarr"',
    '',
    'tmdb:',
    '  api_key: ""',
    '',
    'radarr:',
    '  enabled: false',
    '  url: ""',
    '  api_key: ""',
    '',
    'sonarr:',
    '  enabled: false',
    '  url: ""',
    '  api_key: ""',
    '',
    'prowlarr:',
    '  enabled: false',
    '  url: ""',
    '  api_key: ""',
    '',
    'files:',
    '  recycling_bin: ""',
    '',
    'indexers: []'
)
$cfgLines | Set-Content -Path "$Root\config.yaml.example" -Encoding UTF8
Write-Ok "config.yaml.example written"

# ---- 3. Build frontend ------------------------------------------------------
if (-not $SkipFrontend) {
    Write-Step "3" "Building frontend (npm run build)"
    Push-Location "$Root\frontend"
    npm run build
    Pop-Location
    if ($LASTEXITCODE -ne 0) { Write-Err "npm build failed" }
    Write-Ok "frontend/dist built"
} else {
    Write-Step "3" "Skipping frontend build (-SkipFrontend)"
}

# ---- 4. PyInstaller ---------------------------------------------------------
if (-not $SkipPyInstaller) {
    Write-Step "4" "Running PyInstaller (this takes 2-5 minutes)"
    if (Test-Path "$Root\dist\Slimarr") { Remove-Item "$Root\dist\Slimarr" -Recurse -Force }
    & $PyInstaller "$Root\slimarr.spec" --distpath "$Root\dist" --workpath "$Root\build\pyinstaller" --noconfirm
    if ($LASTEXITCODE -ne 0) { Write-Err "PyInstaller failed" }
    Write-Ok "dist/Slimarr/ created"
} else {
    Write-Step "4" "Skipping PyInstaller (-SkipPyInstaller)"
    if (-not (Test-Path "$Root\dist\Slimarr\Slimarr.exe")) {
        Write-Err "dist/Slimarr/Slimarr.exe not found - build with PyInstaller first"
    }
}

# ---- 5. Inno Setup ----------------------------------------------------------
Write-Step "5" "Building installer with Inno Setup"
New-Item -ItemType Directory -Path "$Root\dist\installer" -Force | Out-Null
& $ISCC "$Root\installer\slimarr.iss"
if ($LASTEXITCODE -ne 0) { Write-Err "Inno Setup failed" }

$installer = Get-ChildItem "$Root\dist\installer\SlimarrSetup*.exe" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
Write-Ok "Installer: $($installer.FullName)"

# ---- Done -------------------------------------------------------------------
Write-Host ""
Write-Host "  Build complete!" -ForegroundColor Green
Write-Host "  Installer: dist\installer\$($installer.Name)" -ForegroundColor White
Write-Host ""
Write-Host "  Share SlimarrSetup-*.exe with others - they just run it." -ForegroundColor Gray
Write-Host ""
