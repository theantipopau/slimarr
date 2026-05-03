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
    # Supported range: 3.11 <= version < 3.14
    # Python 3.14 is NOT supported: lxml and pydantic-core have no prebuilt wheels yet
    # and require Visual C++ Build Tools / Rust to compile from source.
    $MIN_VER = [version]"3.11"
    $MAX_VER = [version]"3.14"  # exclusive upper bound

    $candidates = @(
        @{ Path = "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe"; Args = @() },
        @{ Path = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"; Args = @() },
        @{ Path = "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"; Args = @() },
        @{ Path = "py"; Args = @("-3.13") },
        @{ Path = "py"; Args = @("-3.12") },
        @{ Path = "py"; Args = @("-3.11") },
        @{ Path = "python3"; Args = @() },
        @{ Path = "python"; Args = @() }
    )

    $foundUnsupported = $null

    foreach ($c in $candidates) {
        try {
            $cmd = Get-Command $c.Path -ErrorAction Stop
            $version = & $cmd.Source @($c.Args) -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($LASTEXITCODE -eq 0 -and $version) {
                $v = [version]$version
                if ($v -ge $MIN_VER -and $v -lt $MAX_VER) {
                    return [pscustomobject]@{ File = $cmd.Source; Args = $c.Args; Version = $version }
                } elseif ($v -ge $MAX_VER -and -not $foundUnsupported) {
                    $foundUnsupported = $version
                }
            }
        } catch {}
    }

    if ($foundUnsupported) {
        Write-Host ""
        Write-Host "  Python $foundUnsupported detected but is NOT supported by Slimarr." -ForegroundColor Yellow
        Write-Host "  Python 3.14 does not yet have prebuilt binary packages (wheels) for" -ForegroundColor Yellow
        Write-Host "  lxml and pydantic-core. Installing them requires Visual C++ Build Tools" -ForegroundColor Yellow
        Write-Host "  and Rust, which most users do not have." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  Fix: Install Python 3.12 or 3.13 from https://python.org" -ForegroundColor Cyan
        Write-Host "       Tick 'Add Python to PATH' during install, then rerun install.ps1" -ForegroundColor Cyan
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

function Start-SlimarrUi([string]$PythonExePath) {
    Write-Step "Starting Slimarr"
    Start-Process -FilePath $PythonExePath -ArgumentList @("run.py", "--headless") -WorkingDirectory $Root | Out-Null
    Write-Ok "Slimarr started in background"
    Write-Host "    Waiting for backend to be ready..." -ForegroundColor DarkGray
    $deadline = (Get-Date).AddSeconds(60)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:9494/api/v1/system/health' -TimeoutSec 2 -ErrorAction Stop
            if ($r.StatusCode -ge 200) { $ready = $true; break }
        } catch {}
        Start-Sleep -Milliseconds 500
    }
    Start-Process "http://localhost:9494" | Out-Null
    if ($ready) {
        Write-Ok "Browser opened: http://localhost:9494"
    } else {
        Write-Host "    Backend not ready after 60s — browser opened anyway." -ForegroundColor Yellow
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
    Fail "Python 3.12 or 3.13 was not found. Install from https://python.org and tick 'Add Python to PATH'. Python 3.14 is not yet supported."
}
Write-Ok "Using Python $($Python.Version) at $($Python.File)"

Write-Step "Preparing virtual environment"
$VenvPython = Join-Path $Root "venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    # Check if existing venv is on an unsupported Python version and remove it
    $venvVer = & $VenvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
    if ($LASTEXITCODE -eq 0 -and $venvVer -and [version]$venvVer -ge [version]"3.14") {
        Write-Host "    Removing venv built on Python $venvVer (unsupported)..." -ForegroundColor Yellow
        Remove-Item -LiteralPath (Join-Path $Root "venv") -Recurse -Force
    } else {
        & $VenvPython -m pip --version *> $null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "    Removing broken virtual environment..." -ForegroundColor Yellow
            Remove-Item -LiteralPath (Join-Path $Root "venv") -Recurse -Force
        }
    }
}

if (-not (Test-Path $VenvPython)) {
    Invoke-Python $Python @("-m", "venv", (Join-Path $Root "venv"))
    if ($LASTEXITCODE -ne 0) { Fail "Could not create Python virtual environment." }
}

# Print the exact Python version used in the venv
$venvActualVer = & $VenvPython -c "import sys; print(sys.version)" 2>$null
Write-Ok "Venv Python: $venvActualVer"

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
if ($code -ne 0) {
    Write-Host ""
    Write-Host "  Dependency install failed. Common causes:" -ForegroundColor Yellow
    Write-Host "    - Python 3.14 was used (not yet supported — use 3.12 or 3.13)" -ForegroundColor Yellow
    Write-Host "    - No internet access or firewall blocked PyPI (pypi.org:443)" -ForegroundColor Yellow
    Write-Host "    - Missing Visual C++ Build Tools (only needed if wheels are missing)" -ForegroundColor Yellow
    Write-Host "  See $LogFile for the full error." -ForegroundColor DarkGray
    Fail "Dependency install failed. See above for details."
}
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
    Start-SlimarrUi -PythonExePath $VenvPython
} else {
    Write-Host ""
    Write-Host "  Start now with:" -ForegroundColor White
    Write-Host "    start.bat" -ForegroundColor DarkGray
    Write-Host "    # or: .\venv\Scripts\python.exe run.py --headless" -ForegroundColor DarkGray
}
