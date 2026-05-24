@echo off
setlocal

set "REPO_ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%scripts\start_neuroweave.ps1"

if errorlevel 1 (
    echo.
    echo NeuroWeave failed to start. See data\logs for details.
    pause
)
