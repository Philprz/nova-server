@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
title NOVA - Facturation

:: -----------------------------------------------------------------
:: Arguments :
::   /restart  ou  --restart  ou  /reload
::      Force l'arret du service NOVA-Backend, purge les .pyc obsoletes,
::      puis relance — necessaire pour prendre en compte les modifs de code.
::   /help  ou  --help
::      Affiche l'aide.
:: -----------------------------------------------------------------
set RESTART_MODE=0
if /i "%~1"=="/restart"  set RESTART_MODE=1
if /i "%~1"=="--restart" set RESTART_MODE=1
if /i "%~1"=="/reload"   set RESTART_MODE=1
if /i "%~1"=="/help"     goto SHOW_HELP
if /i "%~1"=="--help"    goto SHOW_HELP
if /i "%~1"=="-h"        goto SHOW_HELP

echo.
echo  ============================================================
if %RESTART_MODE%==1 (
    echo    NOVA - Facturation  ^|  Redemarrage ^(prise en compte des modifs^)
) else (
    echo    NOVA - Facturation  ^|  Demarrage complet
)
echo  ============================================================
echo.

:: ---------------------------------------------------------------
:: [1/4] Demarrage des services
:: ---------------------------------------------------------------
echo  [1/4] Demarrage des services...

:: Verifier l'etat actuel
set BACKEND_RUNNING=0
set TUNNEL_RUNNING=0
sc query NOVA-Backend 2>nul | find "RUNNING" >nul 2>&1 && set BACKEND_RUNNING=1
sc query Cloudflared  2>nul | find "RUNNING" >nul 2>&1 && set TUNNEL_RUNNING=1

:: Mode /restart : forcer l'arret du backend pour reload du code
if not %RESTART_MODE%==1 goto AFTER_RESTART_STOP
if not %BACKEND_RUNNING%==1 goto AFTER_RESTART_STOP

echo        Arret de NOVA-Backend pour reload...
sc stop NOVA-Backend >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  [ERREUR] Impossible d'arreter NOVA-Backend ^(droits admin requis ?^).
    echo  Solution : lancer ce script depuis un terminal administrateur.
    echo.
    pause
    exit /b 1
)

:: Attendre que le service soit STOPPED (max 30s)
set STOP_RETRY=0
:STOP_LOOP
if %STOP_RETRY% geq 15 (
    echo.
    echo  [ERREUR] NOVA-Backend ne s'arrete pas ^(30s ecoules^).
    echo.
    pause
    exit /b 1
)
sc query NOVA-Backend 2>nul | find "STOPPED" >nul 2>&1
if %errorlevel% equ 0 goto STOP_DONE
set /a STOP_RETRY+=1
timeout /t 2 /nobreak >nul
goto STOP_LOOP

:STOP_DONE
set BACKEND_RUNNING=0
echo        NOVA-Backend  [STOPPED]

:: Purge des bytecodes obsoletes pour eviter le piege .pyc stale
:: (cf. lecon 23/02/2026 : routes statiques masquees par bytecode periphe)
echo        Purge des __pycache__...
for /d /r "%~dp0" %%d in (__pycache__) do (
    if exist "%%d" rmdir /S /Q "%%d" >nul 2>&1
)
echo        Bytecodes purges  [OK]

:AFTER_RESTART_STOP

if %BACKEND_RUNNING%==1 if %TUNNEL_RUNNING%==1 (
    echo        Services deja actifs  [OK]
    goto HEALTH_CHECK
)

:: Demarrage NOVA-Backend
if %BACKEND_RUNNING%==0 (
    sc start NOVA-Backend >nul 2>&1
    if !errorlevel! neq 0 (
        echo.
        echo  [ERREUR] Impossible de demarrer NOVA-Backend.
        echo  Solution : relancez nova-setup-tache.bat en administrateur.
        echo.
        pause
        exit /b 1
    )
)

:: Demarrage Cloudflared (tunnel HTTPS)
if %TUNNEL_RUNNING%==0 (
    sc start Cloudflared >nul 2>&1
    if !errorlevel! neq 0 (
        echo.
        echo  [ERREUR] Impossible de demarrer Cloudflared.
        echo  Solution : relancez nova-setup-tache.bat en administrateur.
        echo.
        pause
        exit /b 1
    )
)
echo        Services demarre  [OK]

:: ---------------------------------------------------------------
:: [2/4] Attente que les services soient RUNNING
:: ---------------------------------------------------------------
echo  [2/4] Attente demarrage des services...
set RETRY=0
:SERVICES_LOOP
if %RETRY% geq 10 (
    echo.
    echo  [ERREUR] Les services ne passent pas en RUNNING ^(20s ecoules^).
    echo  Consultez : eventvwr.msc ^> Journaux Windows ^> Application
    echo.
    pause
    exit /b 1
)
set BACKEND_RUNNING=0
set TUNNEL_RUNNING=0
sc query NOVA-Backend 2>nul | find "RUNNING" >nul 2>&1 && set BACKEND_RUNNING=1
sc query Cloudflared  2>nul | find "RUNNING" >nul 2>&1 && set TUNNEL_RUNNING=1
if %BACKEND_RUNNING%==0 (
    set /a RETRY+=1
    timeout /t 2 /nobreak >nul
    goto SERVICES_LOOP
)
if %TUNNEL_RUNNING%==0 (
    set /a RETRY+=1
    timeout /t 2 /nobreak >nul
    goto SERVICES_LOOP
)
echo        NOVA-Backend  [RUNNING]
echo        Cloudflared   [RUNNING]

:: ---------------------------------------------------------------
:: [3/4] Health check FastAPI
:: ---------------------------------------------------------------
:HEALTH_CHECK
echo  [3/4] Verification sante du serveur...
set RETRY=0
:HEALTH_LOOP
if %RETRY% geq 15 (
    echo.
    echo  [ERREUR] Le serveur FastAPI ne repond pas apres 30 secondes.
    echo  Logs : C:\Users\PPZ\NOVA-SERVER\nova.log
    echo.
    pause
    exit /b 1
)
powershell -NoProfile -Command ^
    "try { $r = Invoke-WebRequest -Uri 'http://localhost:8001/health' -UseBasicParsing -TimeoutSec 2; exit ($r.StatusCode -ne 200) } catch { exit 1 }" >nul 2>&1
if %errorlevel% neq 0 (
    set /a RETRY+=1
    set /a ELAPSED=RETRY*2
    <nul set /p "=        Attente... (!ELAPSED!s / 30s)^M"
    timeout /t 2 /nobreak >nul
    goto HEALTH_LOOP
)
echo        Serveur operationnel  [OK]

:: ---------------------------------------------------------------
:: [4/4] Etat final
:: ---------------------------------------------------------------
echo  [4/4] Etat final...
for %%S in (NOVA-Backend Cloudflared) do (
    sc query %%S 2>nul | find "RUNNING" >nul 2>&1
    if !errorlevel! equ 0 (
        echo        %%S  [RUNNING]
    ) else (
        echo        %%S  [STOPPED - VERIFIER]
    )
)

echo.
echo  ============================================================
echo    NOVA pret  ^|  https://nova-rondot.itspirit.ovh
echo  ============================================================
echo.
echo  Interface  : https://nova-rondot.itspirit.ovh/mail-to-biz
echo  API        : http://localhost:8001
echo  Health     : http://localhost:8001/health
echo  Logs       : C:\Users\PPZ\NOVA-SERVER\nova.log
echo.

start "" "https://nova-rondot.itspirit.ovh/mail-to-biz"

endlocal
exit /b 0

:: ---------------------------------------------------------------
:: Aide
:: ---------------------------------------------------------------
:SHOW_HELP
echo.
echo  start-nova.bat [option]
echo.
echo  Sans argument :
echo     Demarre NOVA-Backend et Cloudflared si arretes,
echo     sinon verifie qu'ils repondent ^(health check^).
echo.
echo  /restart , --restart , /reload
echo     Force l'arret de NOVA-Backend, purge les __pycache__
echo     ^(.pyc obsoletes^), puis le relance. Necessaire apres
echo     toute modification de code Python.
echo.
echo  /help , --help , -h
echo     Affiche cette aide.
echo.
echo  Note : peut necessiter un terminal administrateur pour
echo  controler les services Windows.
echo.
endlocal
exit /b 0
