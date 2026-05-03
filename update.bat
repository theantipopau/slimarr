@echo off
echo Updating Slimarr...
echo.

cd /d "%~dp0"

echo [1] Pulling latest code from GitHub...
git pull
if %ERRORLEVEL% neq 0 (
    echo ERROR: git pull failed. Check your internet connection or repo status.
    pause
    exit /b 1
)

echo.
echo [2] Updating Python dependencies...
call venv\Scripts\pip.exe install -r requirements.txt --quiet
if %ERRORLEVEL% neq 0 (
    echo ERROR: pip install failed. Check venv\Scripts\pip.exe exists and PyPI is reachable.
    pause
    exit /b 1
)

echo.
echo [3] Rebuilding frontend...
if exist "frontend\node_modules" (
    cd frontend
    call npm run build --silent
    if %ERRORLEVEL% neq 0 (
        cd ..
        echo WARNING: Frontend build failed. UI may be out of date.
        echo          Run 'cd frontend ^&^& npm install ^&^& npm run build' manually.
    ) else (
        cd ..
        echo    Frontend rebuilt.
    )
) else (
    echo    Skipping frontend build (node_modules not found - run install.ps1 to set up).
)

echo.
echo Update complete! Restart Slimarr for changes to take effect.
echo.
pause
