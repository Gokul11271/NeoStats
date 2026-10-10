@echo off
REM =========================================================================
REM RideWise Assist - One-Click Setup & Launch Script
REM Starts RideWise Assist local Streamlit conversational AI interface
REM =========================================================================

echo.
echo =========================================================================
echo               RideWise Assist - Two-Wheeler & EV Mobility AI
echo =========================================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in your system PATH.
    echo Please install Python 3.10+ from https://www.python.org/ and try again.
    pause
    exit /b 1
)

echo [1/3] Python verified:
python --version

echo.
echo [2/3] Checking & Installing dependencies from requirements.txt...
pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [WARNING] Encountered an issue installing packages, proceeding with launch...
) else (
    echo [OK] All dependencies verified.
)

echo.
echo [3/3] Starting RideWise Assist Streamlit application...
echo Local URL: http://localhost:8501
echo.

python -m streamlit run app.py

pause
