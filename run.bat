@echo off
REM CoolMap AI 실행 (Windows)
cd /d "%~dp0"
python main.py %*
if errorlevel 1 pause
