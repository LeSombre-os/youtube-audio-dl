@echo off
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (python -m pip install -U yt-dlp) else (py -m pip install -U yt-dlp)
if errorlevel 1 pause
