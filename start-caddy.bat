@echo off
echo Demarrage de Caddy pour NOVA...
echo.
echo Interface mail-to-biz accessible sur : http://localhost
echo API directe accessible sur : http://localhost:8000
echo.
caddy run --config Caddyfile
