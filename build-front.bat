@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
title NOVA - Build du front mail-to-biz

echo.
echo  ============================================================
echo    NOVA - Build du front mail-to-biz
echo  ============================================================
echo.

cd /d "%~dp0mail-to-biz"
if errorlevel 1 (
    echo  [ERREUR] Impossible d'acceder au dossier mail-to-biz.
    pause
    exit /b 1
)

echo  [1/2] Lancement de Vite build...
echo.
call npm run build
if errorlevel 1 (
    echo.
    echo  [ERREUR] Build echoue. Voir les logs ci-dessus.
    pause
    exit /b 1
)

echo.
echo  [2/2] Build termine.
echo        Sortie : %~dp0frontend\
echo.
echo  ============================================================
echo    Prochaine etape : commit des changements
echo  ============================================================
echo    git add mail-to-biz/src mail-to-biz/index.html ^
echo            mail-to-biz/tailwind.config.ts frontend/
echo    git commit -m "build: front mail-to-biz"
echo  ============================================================
echo.

endlocal
exit /b 0
