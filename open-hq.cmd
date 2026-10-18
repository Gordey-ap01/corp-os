@echo off
python "%~dp0corp.py" dashboard
if errorlevel 1 exit /b 1
start "" "%~dp0.local\dashboard.html"
