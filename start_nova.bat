@echo off
TITLE NOVA Middleware - Demarrage
COLOR 0A

ECHO ========================================
ECHO    DEMARRAGE NOVA MIDDLEWARE
ECHO ========================================
ECHO.

CD /D C:\Users\PPZ\NOVA

ECHO Activation de l'environnement virtuel...
powershell -Command "& {Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force; . .\venv\Scripts\Activate.ps1}"

ECHO Lancement de FastAPI...
START powershell -NoExit -Command "& {Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force; . .\venv\Scripts\Activate.ps1; uvicorn main:app --reload}"

ECHO Lancement du serveur MCP...
START powershell -NoExit -Command "& {Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force; . .\venv\Scripts\Activate.ps1; python server_mcp.py}"

ECHO.
ECHO NOVA Middleware demarre avec succes!
ECHO.
PAUSE