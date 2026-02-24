@echo off
echo Arret du serveur NOVA...
taskkill /F /FI "WINDOWTITLE eq *python*main.py*" 2>nul
taskkill /F /FI "IMAGENAME eq python.exe" /FI "MEMUSAGE gt 50000" 2>nul
timeout /t 2 /nobreak >nul

echo Demarrage du serveur NOVA...
cd C:\Users\PPZ\NOVA-SERVER
start "NOVA Server" .venv\Scripts\python.exe main.py

echo Serveur redemarre ! Attendre 5 secondes...
timeout /t 5 /nobreak >nul

echo Test de l'endpoint...
curl http://localhost:8000/health | python -m json.tool | findstr "status"

pause
