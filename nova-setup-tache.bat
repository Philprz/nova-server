@echo off
:: ================================================================
:: NOVA - SETUP (a executer UNE SEULE FOIS en administrateur)
:: Modifie les droits ACL des services NOVA-Backend et Cloudflared
:: pour permettre le demarrage sans droits administrateur.
:: ================================================================
chcp 65001 >nul 2>&1
title NOVA - Setup droits services

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERREUR] Ce script doit etre execute en administrateur.
    pause
    exit /b 1
)

echo Verification des services...
sc query NOVA-Backend >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERREUR] Le service NOVA-Backend n'existe pas.
    pause
    exit /b 1
)
sc query Cloudflared >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERREUR] Le service Cloudflared n'existe pas.
    pause
    exit /b 1
)
echo  Services detectes : NOVA-Backend, Cloudflared  [OK]
echo.

echo Modification des droits ACL...
echo.

:: SDDL : ajoute (A;;RPWP;;;AU) = START + STOP pour les utilisateurs authentifies
:: SY=LocalSystem BA=Administrateurs IU=Utilisateurs interactifs SU=Service AU=Tout utilisateur connecte
sc sdset NOVA-Backend "D:(A;;CCLCSWRPWPDTLOCRRC;;;SY)(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)(A;;CCLCSWLOCRRC;;;IU)(A;;CCLCSWLOCRRC;;;SU)(A;;RPWP;;;AU)"
if %errorlevel% equ 0 (
    echo  [OK] NOVA-Backend  : demarrage autorise sans admin
) else (
    echo  [ERREUR] Echec modification ACL NOVA-Backend
)

sc sdset Cloudflared "D:(A;;CCLCSWRPWPDTLOCRRC;;;SY)(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)(A;;CCLCSWLOCRRC;;;IU)(A;;CCLCSWLOCRRC;;;SU)(A;;RPWP;;;AU)"
if %errorlevel% equ 0 (
    echo  [OK] Cloudflared   : demarrage autorise sans admin
) else (
    echo  [ERREUR] Echec modification ACL Cloudflared
)

echo.
echo  Setup termine. start-nova.bat peut maintenant lancer NOVA
echo  par simple double-clic, sans administrateur.
echo.
pause
