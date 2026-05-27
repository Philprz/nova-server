@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
title NOVA - Facturation

echo.
echo  ============================================================
echo    NOVA - Facturation  ^|  Demarrage complet
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
