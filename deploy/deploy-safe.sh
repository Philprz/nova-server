#!/bin/bash
# Script de déploiement SAFE avec backup

SERVER="userbioforce@178.33.233.120"
REMOTE_PATH="/home/userbioforce/NOVA-SERVER"
BACKUP_DATE=$(date +%Y%m%d_%H%M%S)

echo "=== Déploiement SAFE mail-to-biz sur nova.itspirit.ovh ==="
echo ""

# Étape 1 : Créer un backup sur le serveur
echo "📦 Création d'un backup..."
ssh "$SERVER" << ENDSSH
cd $REMOTE_PATH

# Backup du Caddyfile existant
if [ -f Caddyfile ]; then
    cp Caddyfile Caddyfile.backup.$BACKUP_DATE
    echo "✅ Backup créé : Caddyfile.backup.$BACKUP_DATE"
else
    echo "⚠️  Pas de Caddyfile existant"
fi

# Backup du frontend existant
if [ -d frontend ]; then
    cp -r frontend frontend.backup.$BACKUP_DATE
    echo "✅ Backup créé : frontend.backup.$BACKUP_DATE"
else
    echo "⚠️  Pas de dossier frontend existant"
fi

ENDSSH

echo ""
read -p "Continuer le déploiement ? (o/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Oo]$ ]]; then
    echo "❌ Déploiement annulé"
    exit 1
fi

# Étape 2 : Copier les nouveaux fichiers
echo ""
echo "📤 Copie du Caddyfile..."
scp Caddyfile "$SERVER:$REMOTE_PATH/"

echo "📤 Copie du frontend..."
scp -r frontend "$SERVER:$REMOTE_PATH/"

echo ""
echo "✅ Fichiers déployés!"
echo ""
echo "⚠️  IMPORTANT : Testez avant de redémarrer Caddy :"
echo ""
echo "  ssh $SERVER"
echo "  cd $REMOTE_PATH"
echo "  caddy validate --config Caddyfile"
echo ""
echo "Si validation OK :"
echo "  sudo systemctl reload caddy"
echo ""
echo "Si problème, restaurer le backup :"
echo "  cp Caddyfile.backup.$BACKUP_DATE Caddyfile"
echo "  sudo systemctl reload caddy"
echo ""
