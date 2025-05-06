@echo off
REM — aller dans le dossier du projet
cd /d C:\Users\PPZ\NOVA
REM — activer l’environnement virtuel (si tu en as un)
call C:\Users\PPZ\NOVA\venv\Scripts\activate.bat
REM — lancer le worker
python worker.py >> logs\worker.log 2>&1
