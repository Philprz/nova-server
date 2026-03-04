@echo off
echo Arret du serveur NOVA...

REM Trouver uniquement le PID de NOVA (.venv\Scripts\python.exe main.py)
REM ATTENTION : Ne PAS tuer C:\Python\python.exe qui appartient a BIOFORCE (port 8000)
for /f "tokens=2 delims=," %%i in ('wmic process where "ExecutablePath like '%%NOVA-SERVER\%%venv%%' and CommandLine like '%%main.py%%'" get ProcessId /format:csv 2^>nul ^| findstr /r "[0-9]"') do (
    echo Arret PID %%i (NOVA)...
    taskkill /F /PID %%i 2>nul
)

timeout /t 2 /nobreak >nul

echo Demarrage du serveur NOVA...
cd C:\Users\PPZ\NOVA-SERVER
start "NOVA Server" .venv\Scripts\python.exe main.py

echo Serveur redemarre ! Attendre 5 secondes...
timeout /t 5 /nobreak >nul

echo Test de l'endpoint...
curl http://localhost:8001/health | python -m json.tool | findstr "status"

pause
