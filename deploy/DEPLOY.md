# Déploiement mail-to-biz sur nova.itspirit.ovh

⚠️ **IMPORTANT : Ne pas casser l'existant !**

## Fichiers à déployer

1. `Caddyfile` - Configuration Caddy mise à jour
2. `frontend/` - Application React buildée

## ÉTAPE 0 : Vérifier l'existant (OBLIGATOIRE)

Avant tout déploiement, vérifiez ce qui existe :

```bash
cd c:\Users\PPZ\NOVA-SERVER\deploy
bash check-server.sh
```

Notez :
- L'emplacement du NOVA-SERVER sur le serveur
- Si un Caddyfile existe déjà
- Si un dossier frontend existe
- Comment Caddy est lancé (service ou commande)

## Instructions de déploiement

### Option 1 : Déploiement SAFE avec backup automatique (RECOMMANDÉ)

```bash
cd c:\Users\PPZ\NOVA-SERVER\deploy
bash deploy-safe.sh
```

Ce script va :
1. ✅ Créer un backup automatique du Caddyfile et frontend existants
2. ✅ Copier les nouveaux fichiers
3. ✅ Vous donner les commandes pour tester et restaurer si besoin

### Option 2 : Via SCP manuel

```bash
# Depuis Windows (Git Bash ou WSL)
cd c:\Users\PPZ\NOVA-SERVER\deploy

# Copier le Caddyfile
scp Caddyfile userbioforce@178.33.233.120:/home/userbioforce/NOVA-SERVER/

# Copier le frontend
scp -r frontend userbioforce@178.33.233.120:/home/userbioforce/NOVA-SERVER/
```

### Option 2 : Via Git (si le repo existe sur le serveur)

```bash
# Sur le serveur
ssh userbioforce@178.33.233.120
cd NOVA-SERVER
git pull origin main
```

### Étapes sur le serveur

Une fois connecté en SSH au serveur :

```bash
# 1. Aller dans le répertoire NOVA
cd /home/userbioforce/NOVA-SERVER  # ou le chemin correct

# 2. Vérifier la configuration Caddy
caddy validate --config Caddyfile

# 3. Redémarrer Caddy
sudo systemctl reload caddy
# ou si Caddy n'est pas un service :
pkill caddy
caddy run --config Caddyfile &

# 4. Vérifier que le serveur NOVA tourne
ps aux | grep python
# Si non, démarrer :
python3 main.py &
```

## Vérification

```bash
# Tester l'interface
curl https://nova.itspirit.ovh/

# Tester l'API
curl https://nova.itspirit.ovh/api/sap-rondot/status
```

## Troubleshooting

Si 502 Bad Gateway :
1. Vérifier que NOVA tourne sur port 8000 : `netstat -tlnp | grep 8000`
2. Vérifier les logs Caddy : `journalctl -u caddy -f`
3. Vérifier les logs NOVA : `tail -f nova.log`

Si certificat SSL non valide :
- Caddy obtient automatiquement les certificats Let's Encrypt
- Vérifier que le port 80 et 443 sont ouverts
- Vérifier les logs : `caddy logs`
