@echo off
title NOVA Middleware - Démarrage
color 0A
echo =========================================
echo    DEMARRAGE NOVA MIDDLEWARE
echo =========================================
echo.
echo Préparation de l'environnement...
cd /d C:\Users\PPZ\NOVA
echo.
echo Lancement du script PowerShell...
powershell -ExecutionPolicy Bypass -File ".\automated_start.ps1"
echo.
echo Si les fenêtres des serveurs se sont ouvertes, le système est opérationnel.
echo.
echo Appuyez sur une touche pour fermer cette fenêtre...
pause > nul