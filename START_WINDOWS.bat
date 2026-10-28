@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3 run_demo.py %*
) else (
    python run_demo.py %*
)
if errorlevel 1 (
    echo.
    echo Python 3.10 or newer is required. See README.md and any error above.
    pause
)
