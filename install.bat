@echo off
REM Installation script for media sorting utility (Windows)

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%venv"
set "REQUIREMENTS=%SCRIPT_DIR%requirements.txt"

echo ==========================================
echo Media Sorting Utility - Installation
echo ==========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH.
    echo Please install Python 3 from https://www.python.org/
    exit /b 1
)

REM Create virtual environment
echo Creating virtual environment...
python -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo Error: Failed to create virtual environment.
    exit /b 1
)

REM Activate virtual environment
echo Activating virtual environment...
call "%VENV_DIR%\Scripts\activate.bat"

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip --quiet

REM Install dependencies
echo Installing dependencies...
pip install -r "%REQUIREMENTS%"
if errorlevel 1 (
    echo Error: Failed to install dependencies.
    exit /b 1
)

echo.
echo ==========================================
echo Installation complete!
echo ==========================================
echo.
echo To run the utility, use: run.bat
echo Or activate manually: venv\Scripts\activate.bat ^&^& python main.py

endlocal

