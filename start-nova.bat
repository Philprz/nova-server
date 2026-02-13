@echo off
REM ============================================
REM  NOVA-SERVER - Script de demarrage complet
REM  Lance Backend (FastAPI) + Frontend (React)
REM ============================================

echo.
echo ========================================
echo   NOVA-SERVER v2.3.0
echo   Demarrage Backend + Frontend
echo ========================================
echo.

REM Verifier Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python non trouve. Veuillez installer Python 3.9+
    pause
    exit /b 1
)

echo [OK] Python detecte
echo.

REM Verifier dossier mail-to-biz
if not exist "mail-to-biz\" (
    echo [ERREUR] Dossier mail-to-biz introuvable
    pause
    exit /b 1
)

REM Demarrer Backend FastAPI en arriere-plan
echo ========================================
echo   1/2 - Demarrage Backend FastAPI
echo ========================================
echo.
echo Demarrage serveur FastAPI sur http://localhost:8001...
start "NOVA Backend" cmd /k "python main.py"

REM Attendre que le backend demarre
timeout /t 5 /nobreak >nul

REM Verifier si Node.js est installe
where node >nul 2>&1
if errorlevel 1 (
    echo.
    echo [INFO] Node.js non trouve - Frontend deja compile
    echo Le frontend sera servi par FastAPI sur http://localhost:8001/mail-to-biz
    echo.
    goto :backend_only
)

REM Verifier si le frontend source existe
if not exist "mail-to-biz\src\" (
    echo.
    echo [INFO] Frontend source non trouve - Utilisation du build
    echo Le frontend sera servi par FastAPI sur http://localhost:8001/mail-to-biz
    echo.
    goto :backend_only
)

REM Demarrer Frontend React Dev Server
echo.
echo ========================================
echo   2/2 - Demarrage Frontend React Dev
echo ========================================
echo.
echo Demarrage React Dev Server...
cd mail-to-biz
start "NOVA Frontend" cmd /k "npm run dev"
cd ..

echo.
echo ========================================
echo   NOVA DEMARRE AVEC SUCCES!
echo ========================================
echo.
echo Backend FastAPI : http://localhost:8001
echo Frontend React Dev : http://localhost:5173 (si disponible)
echo Mail-to-Biz : http://localhost:8001/mail-to-biz
echo NOVA Assistant : http://localhost:8001/interface/itspirit
echo API Docs : http://localhost:8001/docs
echo.
echo Appuyez sur une touche pour arreter tous les services...
pause >nul
goto :end

:backend_only
echo.
echo ========================================
echo   NOVA DEMARRE (Backend uniquement)
echo ========================================
echo.
echo Backend FastAPI : http://localhost:8001
echo Mail-to-Biz : http://localhost:8001/mail-to-biz
echo NOVA Assistant : http://localhost:8001/interface/itspirit
echo API Docs : http://localhost:8001/docs
echo.
echo Le frontend compile est servi par FastAPI.
echo.
echo Appuyez sur une touche pour arreter le backend...
pause >nul
goto :end

:end
REM Arreter les processus
echo.
echo Arret des services NOVA...
taskkill /FI "WINDOWTITLE eq NOVA Backend*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq NOVA Frontend*" /F >nul 2>&1
echo Services arretes.
echo.
