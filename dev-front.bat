@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
title NOVA - Watch front mail-to-biz (auto-rebuild)

echo.
echo  ============================================================
echo    NOVA - Watch front mail-to-biz
echo  ============================================================
echo.
echo    Cette fenetre surveille mail-to-biz/src/ en continu.
echo    A chaque sauvegarde d'un fichier, Vite rebuild vers
echo    frontend/ et FastAPI sert directement la nouvelle version.
echo.
echo    Workflow :
echo      1. Modifier un fichier dans mail-to-biz/src/
echo      2. Ctrl+S pour sauvegarder
echo      3. Attendre 1-2s ("built in X.Xs" ci-dessous)
echo      4. Ctrl+F5 sur le navigateur
echo.
echo    Pour arreter le watcher : Ctrl+C dans cette fenetre.
echo  ============================================================
echo.

cd /d "%~dp0mail-to-biz"
if errorlevel 1 (
    echo  [ERREUR] Impossible d'acceder au dossier mail-to-biz.
    pause
    exit /b 1
)

call npm run build:watch

endlocal
