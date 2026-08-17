@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo Pixel Forge could not start because .venv was not found.
    echo Create the virtual environment and install the project requirements first.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"
start "" ".venv\Scripts\pythonw.exe" "%~dp0main.py"

endlocal
exit /b 0
