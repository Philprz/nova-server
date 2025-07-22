@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
set PYTHONIOENCODING=utf-8

REM quick_fix_nova.bat - Script de correction rapide pour NOVA sur Windows
REM Executez ce script pour appliquer les corrections rapidement

echo.
echo ========================================
echo  NOVA - CORRECTION RAPIDE DES ERREURS
echo ========================================
echo.

REM Verification de Python
echo [1/6] Verification de Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERREUR: Python non trouve dans PATH
    echo Installez Python 3.8+ et ajoutez-le au PATH
    pause
    exit /b 1
)

REM Extraction de la version brute de Python
for /f "tokens=2 delims= " %%a in ('python --version 2^>^&1') do set PYTHON_VERSION=%%a
echo Version detectee: !PYTHON_VERSION!

REM Extraction de la version majeure et mineure
for /f "tokens=1,2 delims=." %%a in ("!PYTHON_VERSION!") do (
    set PYTHON_VERSION_MAJOR=%%a
    set PYTHON_VERSION_MINOR=%%b
)

REM Conversion en nombre pour la comparaison
set /a PYTHON_VERSION_NUM=!PYTHON_VERSION_MAJOR!*100 + !PYTHON_VERSION_MINOR!

REM Comparaison de la version
if !PYTHON_VERSION_NUM! LSS 308 (
    echo ERREUR: Version de Python incorrecte. Version 3.8+ requise.
    pause
    exit /b 1
)
echo [OK] Python !PYTHON_VERSION! detecte

REM Configuration de l'encodage
echo [2/6] Configuration encodage UTF-8...
echo [OK] Encodage UTF-8 configure

REM Creation des dossiers requis
echo [3/6] Creation des dossiers requis...
if not exist "logs" mkdir logs
if not exist "cache" mkdir cache  
if not exist "static" mkdir static
echo [OK] Dossiers crees

REM Verification et creation du fichier .env
echo [4/6] Verification fichier .env...
if not exist ".env" (
    if exist ".env.template" (
        copy ".env.template" ".env" >nul
        echo [WARNING] Fichier .env cree a partir du template
        echo    Editez .env avec vos vraies valeurs API
    ) else (
        echo [ERROR] Fichier .env.template manquant
        echo Creez manuellement le fichier .env
    )
) else (
    echo [OK] Fichier .env existe
)

REM Installation/verification des dependances critiques
echo [5/6] Verification des dependances...
python -c "import fastapi, uvicorn, anthropic, httpx" >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Dependances manquantes - Installation...
    python -m pip install fastapi uvicorn anthropic httpx openai simple-salesforce python-dotenv aiofiles python-multipart
    if errorlevel 1 (
        echo [ERROR] Echec installation des dependances
        echo Executez manuellement: pip install -r requirements.txt
        pause
        exit /b 1
    )
    echo [OK] Dependances installees
) else (
    echo [OK] Dependances presentes
)

REM Test de demarrage
echo [6/6] Test de demarrage NOVA...
echo.
echo ========================================
echo  DEMARRAGE DE NOVA
echo ========================================
echo.
echo Interface:       http://localhost:8000/api/assistant/interface
echo Documentation:   http://localhost:8000/docs  
echo Sante:          http://localhost:8000/health
echo.
echo Appuyez sur Ctrl+C pour arreter le serveur
echo.

REM Lancement avec gestion d'erreur
python startup_script.py
if errorlevel 1 (
    echo.
    echo [ERROR] Echec du demarrage de NOVA
    echo Consultez les logs dans startup.log
    pause
    exit /b 1
)

echo.
echo [OK] NOVA arrete proprement
pause
