#!/bin/bash
# Script de déploiement pour nova.itspirit.ovh

SERVER="userbioforce@178.33.233.120"
REMOTE_PATH="/home/userbioforce/NOVA-SERVER"

echo "=== Déploiement mail-to-biz sur nova.itspirit.ovh ==="
echo ""

# Copier le Caddyfile
echo "📦 Copie du Caddyfile..."
scp Caddyfile "$SERVER:$REMOTE_PATH/"

# Copier le frontend
echo "📦 Copie du frontend..."
scp -r frontend "$SERVER:$REMOTE_PATH/"

echo ""
echo "✅ Fichiers copiés!"
echo ""
echo "Maintenant, connectez-vous au serveur et exécutez :"
echo "  ssh $SERVER"
echo "  cd $REMOTE_PATH"
echo "  caddy validate --config Caddyfile"
echo "  sudo systemctl reload caddy"
echo ""
