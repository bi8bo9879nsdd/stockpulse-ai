@echo off
setlocal

cd /d "%~dp0"
title StockPulse AI

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Project virtual environment was not found:
    echo %PYTHON_EXE%
    echo.
    echo Please follow the installation section in README.md first.
    echo.
    pause
    exit /b 1
)

echo Starting StockPulse AI...
echo Local URL: http://localhost:8501
echo Close this window to stop the local service.
echo.

"%PYTHON_EXE%" -m streamlit run app.py --server.port=8501 --server.headless=false --browser.gatherUsageStats=false

if errorlevel 1 (
    echo.
    echo [ERROR] StockPulse AI failed to start. Review the log above.
    pause
)

endlocal
