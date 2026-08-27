@echo off
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (python app.py) else (py app.py)
if errorlevel 1 pause
