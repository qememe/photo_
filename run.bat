@echo off
REM Run script for media sorting utility (Windows)

setlocal

set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%venv"
set "MAIN_SCRIPT=%SCRIPT_DIR%main.py"

REM Check if venv exists
if not exist "%VENV_DIR%" (
    echo Error: Virtual environment not found.
    echo Please run install.bat first
    exit /b 1
)

REM Activate virtual environment
call "%VENV_DIR%\Scripts\activate.bat"

REM Run main script
python "%MAIN_SCRIPT%"

endlocal

