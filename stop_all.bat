@echo off
cd /d %~dp0
powershell -ExecutionPolicy Bypass -File ".\stop_all.ps1"
pause
