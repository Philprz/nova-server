#!/bin/bash
# Script de vérification du serveur avant déploiement

SERVER="userbioforce@178.33.233.120"

echo "=== Vérification du serveur nova.itspirit.ovh ==="
echo ""
echo "🔍 Connexion au serveur..."
echo ""

ssh "$SERVER" << 'ENDSSH'
echo "📁 Structure des dossiers :"
ls -la ~/ | grep -i nova

echo ""
echo "🔧 Caddy installé ?"
which caddy && caddy version

echo ""
echo "📄 Caddyfile existant ?"
find ~/ -name "Caddyfile" 2>/dev/null

echo ""
echo "🐍 Python/NOVA en cours d'exécution ?"
ps aux | grep python | grep -v grep

echo ""
echo "🌐 Ports en écoute :"
netstat -tlnp 2>/dev/null | grep -E ':80|:443|:8000' || ss -tlnp | grep -E ':80|:443|:8000'

echo ""
echo "📋 Service Caddy ?"
systemctl status caddy 2>/dev/null | head -5 || echo "Pas de service systemd"

ENDSSH

echo ""
echo "✅ Vérification terminée"
