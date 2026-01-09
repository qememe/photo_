@echo off
REM Ускоренная установка пакетов
REM Installation script for media sorting utility (Windows)
REM Исправлены пути Windows и оптимизирован батник установки

setlocal enabledelayedexpansion

cls

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

REM Check if virtual environment exists, if not create it
if exist "%VENV_DIR%" (
    echo Virtual environment already exists, activating...
    call "%VENV_DIR%\Scripts\activate.bat"
) else (
    echo Creating virtual environment...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo Error: Failed to create virtual environment.
        exit /b 1
    )
    echo Activating virtual environment...
    call "%VENV_DIR%\Scripts\activate.bat"
)

REM Upgrade pip first (ускоренная установка пакетов)
echo Upgrading pip...
python -m pip install --upgrade pip --quiet

REM Ускоренная установка пакетов: --no-cache-dir для быстрой установки без кэша
echo Installing dependencies (fast mode, no cache)...
pip install --no-cache-dir --upgrade -r "%REQUIREMENTS%"
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
