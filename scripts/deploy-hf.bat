@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy-hf.ps1"
echo.
pause
