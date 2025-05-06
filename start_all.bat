@echo off
cd /d %~dp0
powershell -ExecutionPolicy Bypass -File ".\start_all.ps1"
pause
