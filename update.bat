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
    echo ERROR: pip install failed.
    pause
    exit /b 1
)

echo.
echo Update complete! Restart Slimarr for changes to take effect.
echo.
pause
