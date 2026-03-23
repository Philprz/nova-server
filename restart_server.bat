@echo off
echo Arret du serveur NOVA (port 8001)...

REM Tuer le process sur le port 8001
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8001 " ^| findstr "LISTENING"') do (
    echo Arret PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

timeout /t 2 /nobreak >nul

echo Demarrage NOVA...
cd /d C:\Users\PPZ\NOVA-SERVER
.venv\Scripts\python.exe main.py
