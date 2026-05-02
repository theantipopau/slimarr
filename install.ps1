# install.ps1 -- Slimarr source/portable installer for Windows
#
# Usage:
#   .\install.ps1
#   .\install.ps1 -SkipFrontend
#   .\install.ps1 -InstallService
#   .\install.ps1 -Uninstall
#   .\install.ps1 -Start

param(
    [switch]$SkipFrontend,
    [switch]$InstallService,
    [switch]$Uninstall,
    [switch]$Start
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$ServiceName = "Slimarr"
$LogFile = Join-Path $Root "startup-error.log"

function Write-Step($Message) {
    Write-Host ""
    Write-Host "  $Message" -ForegroundColor Cyan
}

function Write-Ok($Message) {
    Write-Host "    OK: $Message" -ForegroundColor Green
}

function Fail($Message) {
    Write-Host ""
    Write-Host "  ERROR: $Message" -ForegroundColor Red
    Write-Host "  Log: $LogFile" -ForegroundColor DarkGray
    exit 1
}

function Resolve-Python {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "py",
        "python3",
        "python"
    )

    foreach ($candidate in $candidates) {
        try {
            $cmd = Get-Command $candidate -ErrorAction Stop
            if ($candidate -eq "py") {
                $version = & $cmd.Source -3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
                if ($LASTEXITCODE -eq 0 -and [version]$version -ge [version]"3.11") {
                    return [pscustomobject]@{ File = $cmd.Source; Args = @("-3") }
                }
            } else {
                $version = & $cmd.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
                if ($LASTEXITCODE -eq 0 -and [version]$version -ge [version]"3.11") {
                    return [pscustomobject]@{ File = $cmd.Source; Args = @() }
                }
            }
        } catch {}
    }

    return $null
}

function Invoke-Python($Python, [string[]]$ArgsToPass) {
    & $Python.File @($Python.Args) @ArgsToPass
}

function Invoke-LoggedNative([scriptblock]$Command) {
    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Command *>> $LogFile
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $oldPreference
    }
}

function Ensure-Config {
    $example = Join-Path $Root "config.yaml.example"
    $config = Join-Path $Root "config.yaml"

    if (-not (Test-Path $config)) {
        if (Test-Path $example) {
            Copy-Item $example $config
        } else {
            @"
server:
  host: "0.0.0.0"
  port: 9494
  log_level: "info"

auth:
  secret_key: ""
  api_key: ""

download_client: "sabnzbd"

files:
  recycling_bin: "./data/recycling"
"@ | Set-Content $config -Encoding UTF8
        }
        Write-Ok "Created config.yaml"
    } else {
        Write-Ok "config.yaml already exists"
    }
}

if ($Uninstall) {
    Write-Step "Removing Windows service"
    if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
        sc.exe delete $ServiceName | Out-Null
        Write-Ok "Service removed"
    } else {
        Write-Ok "Service was not installed"
    }
    exit 0
}

Write-Host ""
Write-Host "  Slimarr Installer" -ForegroundColor Green
Write-Host "  =================" -ForegroundColor DarkGreen

Write-Step "Checking Python"
$Python = Resolve-Python
if (-not $Python) {
    Fail "Python 3.11 or newer was not found. Install it from https://python.org and tick 'Add Python to PATH'."
}
Write-Ok "Using $($Python.File) $($Python.Args -join ' ')"

Write-Step "Preparing virtual environment"
$VenvPython = Join-Path $Root "venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    & $VenvPython -m pip --version *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "    Removing broken virtual environment..." -ForegroundColor Yellow
        Remove-Item -LiteralPath (Join-Path $Root "venv") -Recurse -Force
    }
}

if (-not (Test-Path $VenvPython)) {
    Invoke-Python $Python @("-m", "venv", (Join-Path $Root "venv"))
    if ($LASTEXITCODE -ne 0) { Fail "Could not create Python virtual environment." }
}

& $VenvPython -m pip --version *> $null
if ($LASTEXITCODE -ne 0) {
    $code = Invoke-LoggedNative { & $VenvPython -m ensurepip --upgrade }
    if ($code -ne 0) { Fail "Could not bootstrap pip." }
}
$code = Invoke-LoggedNative { & $VenvPython -m pip install --upgrade pip -q }
if ($code -ne 0) {
    Write-Host "    Could not upgrade pip; continuing with the existing pip." -ForegroundColor Yellow
}
Write-Ok "Virtual environment ready"

Write-Step "Installing Python dependencies"
$requirements = Join-Path $Root "requirements.txt"
$code = Invoke-LoggedNative { & $VenvPython -m pip install -r $requirements -q }
if ($code -ne 0) { Fail "Dependency install failed." }
Write-Ok "Python dependencies installed"

if (-not $SkipFrontend) {
    Write-Step "Building frontend"
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Fail "npm was not found. Install Node.js 18 or newer from https://nodejs.org, or rerun with -SkipFrontend if frontend\\dist already exists."
    }

    Push-Location (Join-Path $Root "frontend")
    $code = Invoke-LoggedNative { npm install --silent }
    if ($code -ne 0) {
        Pop-Location
        Fail "npm install failed."
    }
    $code = Invoke-LoggedNative { npm run build }
    if ($code -ne 0) {
        Pop-Location
        Fail "frontend build failed."
    }
    Pop-Location
    Write-Ok "frontend/dist built"
} else {
    if (-not (Test-Path (Join-Path $Root "frontend\dist\index.html"))) {
        Fail "-SkipFrontend was used but frontend\\dist\\index.html does not exist."
    }
    Write-Ok "Skipped frontend build"
}

Write-Step "Preparing config and data directories"
foreach ($dir in @("data", "data\logs", "data\MediaCover", "data\recycling")) {
    New-Item -ItemType Directory -Path (Join-Path $Root $dir) -Force | Out-Null
}
Ensure-Config
Write-Ok "Data directories ready"

if ($InstallService) {
    Write-Step "Installing Windows service"
    $binPath = "`"$VenvPython`" `"$Root\run.py`" --headless"
    if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
        sc.exe delete $ServiceName | Out-Null
        Start-Sleep -Seconds 1
    }
    sc.exe create $ServiceName binpath= $binPath start= auto DisplayName= "Slimarr" | Out-Null
    sc.exe description $ServiceName "Slimarr - Smart Plex media replacement manager" | Out-Null
    sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/10000/restart/30000 | Out-Null
    Start-Service -Name $ServiceName
    Write-Ok "Service installed and started"
}

Write-Host ""
Write-Host "  Installation complete." -ForegroundColor Green
Write-Host "  Web UI: http://localhost:9494" -ForegroundColor White
Write-Host "  Logs:   $Root\data\logs" -ForegroundColor DarkGray

if ($Start) {
    Write-Step "Starting Slimarr"
    & $VenvPython (Join-Path $Root "run.py") --headless
} else {
    Write-Host ""
    Write-Host "  Start now with:" -ForegroundColor White
    Write-Host "    .\venv\Scripts\python.exe run.py --headless" -ForegroundColor DarkGray
}
