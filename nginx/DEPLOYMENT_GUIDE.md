# Guide de Déploiement - nova-rondot.itspirit.ovh

## 🎯 Objectif

Servir l'application **mail-to-biz** sur le domaine `https://nova-rondot.itspirit.ovh/` via un reverse proxy Nginx.

---

## 📋 Prérequis

### Serveur
- VPS/Serveur Linux (Ubuntu 20.04+ / Debian 11+ recommandé)
- Accès SSH root ou sudo
- Domaine pointant vers l'IP du serveur

### DNS
Configurer l'enregistrement DNS :
```
Type: A
Nom: nova-rondot
Valeur: <IP_DU_SERVEUR>
TTL: 3600
```

Vérifier la propagation DNS :
```bash
ping nova-rondot.itspirit.ovh
nslookup nova-rondot.itspirit.ovh
```

---

## 🚀 Installation Nginx

### Ubuntu/Debian
```bash
sudo apt update
sudo apt install nginx -y
sudo systemctl enable nginx
sudo systemctl start nginx
```

### CentOS/RHEL
```bash
sudo yum install epel-release -y
sudo yum install nginx -y
sudo systemctl enable nginx
sudo systemctl start nginx
```

---

## 🔐 Installation Certificat SSL (Let's Encrypt)

### 1. Installer Certbot
```bash
# Ubuntu/Debian
sudo apt install certbot python3-certbot-nginx -y

# CentOS/RHEL
sudo yum install certbot python3-certbot-nginx -y
```

### 2. Obtenir le certificat SSL
```bash
sudo certbot --nginx -d nova-rondot.itspirit.ovh
```

**Suivre les instructions :**
- Entrer votre email
- Accepter les conditions
- Choisir : Rediriger HTTP vers HTTPS (option 2)

Le certificat sera automatiquement installé et renouvelé.

### 3. Vérifier le renouvellement automatique
```bash
sudo certbot renew --dry-run
```

---

## ⚙️ Configuration Nginx

### 1. Copier la configuration
```bash
sudo cp nginx/nova-rondot.conf /etc/nginx/sites-available/nova-rondot.conf
```

### 2. Créer le lien symbolique
```bash
sudo ln -s /etc/nginx/sites-available/nova-rondot.conf /etc/nginx/sites-enabled/
```

### 3. Supprimer la configuration par défaut (optionnel)
```bash
sudo rm /etc/nginx/sites-enabled/default
```

### 4. Tester la configuration
```bash
sudo nginx -t
```

**Résultat attendu :**
```
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

### 5. Recharger Nginx
```bash
sudo systemctl reload nginx
```

---

## 🐍 Démarrer le Backend NOVA

### 1. Configurer le backend pour le déploiement

**Modifier `.env` :**
```env
# Mode production
NOVA_MODE=production

# Host et port
APP_HOST=127.0.0.1  # Écoute uniquement localhost (sécurisé)
APP_PORT=8000

# Désactiver le reload automatique
UVICORN_RELOAD=false
```

### 2. Créer un service systemd

**Fichier : `/etc/systemd/system/nova-server.service`**
```ini
[Unit]
Description=NOVA-SERVER Backend FastAPI
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/home/nova/NOVA-SERVER
Environment="PATH=/home/nova/NOVA-SERVER/.venv/bin"
ExecStart=/home/nova/NOVA-SERVER/.venv/bin/python main.py
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

**Ajuster les chemins selon votre installation !**

### 3. Activer et démarrer le service
```bash
sudo systemctl daemon-reload
sudo systemctl enable nova-server
sudo systemctl start nova-server
```

### 4. Vérifier le statut
```bash
sudo systemctl status nova-server
```

### 5. Voir les logs
```bash
sudo journalctl -u nova-server -f
```

---

## ✅ Vérification

### 1. Tester le backend directement
```bash
curl http://127.0.0.1:8000/health
```

**Réponse attendue :**
```json
{
  "service": "NOVA Server",
  "status": "active",
  "timestamp": "2026-02-09T10:30:00"
}
```

### 2. Tester via le domaine
```bash
curl https://nova-rondot.itspirit.ovh/health
```

### 3. Tester mail-to-biz
Ouvrir dans un navigateur :
```
https://nova-rondot.itspirit.ovh/
```

Doit rediriger automatiquement vers :
```
https://nova-rondot.itspirit.ovh/mail-to-biz
```

---

## 🔧 Configuration Avancée

### 1. Ajuster les limites Nginx

**Fichier : `/etc/nginx/nginx.conf`**
```nginx
http {
    # Augmenter les limites
    client_max_body_size 50M;
    client_body_buffer_size 128k;

    # Timeouts
    proxy_connect_timeout 75s;
    proxy_send_timeout 300s;
    proxy_read_timeout 300s;

    # Logs
    access_log /var/log/nginx/access.log;
    error_log /var/log/nginx/error.log warn;

    # Compression
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;
}
```

### 2. Activer le cache (optionnel)
```nginx
# Dans server block
location /mail-to-biz/assets {
    proxy_pass http://127.0.0.1:8000/mail-to-biz/assets;
    proxy_cache_valid 200 1h;
    add_header X-Cache-Status $upstream_cache_status;
}
```

### 3. Rate limiting (protection DDoS)
```nginx
# Dans http block
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;

# Dans location /api
limit_req zone=api burst=20 nodelay;
```

---

## 🐛 Dépannage

### Problème : 502 Bad Gateway

**Causes possibles :**
1. Backend non démarré
2. Port 8000 non accessible
3. Configuration proxy incorrecte

**Solutions :**
```bash
# Vérifier le backend
sudo systemctl status nova-server
curl http://127.0.0.1:8000/health

# Vérifier les logs Nginx
sudo tail -f /var/log/nginx/nova-rondot.error.log

# Vérifier les logs NOVA
sudo journalctl -u nova-server -f
```

### Problème : 403 Forbidden

**Cause :** Permissions fichiers incorrectes

**Solution :**
```bash
sudo chown -R www-data:www-data /home/nova/NOVA-SERVER
sudo chmod -R 755 /home/nova/NOVA-SERVER
```

### Problème : SSL Certificate Error

**Cause :** Certificat expiré ou non trouvé

**Solution :**
```bash
# Renouveler manuellement
sudo certbot renew

# Vérifier la config SSL
sudo nginx -t

# Recharger Nginx
sudo systemctl reload nginx
```

### Problème : WebSocket non fonctionnel

**Cause :** Headers Upgrade manquants

**Vérifier la configuration :**
```nginx
location /ws {
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

---

## 📊 Monitoring

### 1. Vérifier les logs en temps réel
```bash
# Logs Nginx
sudo tail -f /var/log/nginx/nova-rondot.access.log
sudo tail -f /var/log/nginx/nova-rondot.error.log

# Logs NOVA Backend
sudo journalctl -u nova-server -f
```

### 2. Statistiques Nginx
```bash
# Connexions actives
sudo nginx -V 2>&1 | grep -o with-http_stub_status_module

# Si disponible, ajouter dans la config :
location /nginx_status {
    stub_status on;
    access_log off;
    allow 127.0.0.1;
    deny all;
}
```

### 3. Surveiller les performances
```bash
# CPU/RAM
htop

# Connexions réseau
netstat -tuln | grep :8000
ss -tuln | grep :8000
```

---

## 🔄 Mises à Jour

### Mettre à jour NOVA

```bash
# Se connecter au serveur
ssh user@nova-rondot.itspirit.ovh

# Aller dans le dossier NOVA
cd /home/nova/NOVA-SERVER

# Récupérer les dernières modifications
git pull

# Installer les dépendances
source .venv/bin/activate
pip install -r requirements.txt

# Redémarrer le service
sudo systemctl restart nova-server

# Vérifier
sudo systemctl status nova-server
```

### Mettre à jour Nginx

```bash
sudo apt update
sudo apt upgrade nginx -y
sudo systemctl reload nginx
```

---

## 🔐 Sécurité

### 1. Pare-feu (UFW)
```bash
# Installer UFW
sudo apt install ufw -y

# Configurer
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 'Nginx Full'
sudo ufw enable

# Vérifier
sudo ufw status
```

### 2. Fail2Ban (protection SSH)
```bash
# Installer
sudo apt install fail2ban -y

# Créer config
sudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local

# Éditer
sudo nano /etc/fail2ban/jail.local

# Activer
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### 3. Sauvegardes
```bash
# Backup automatique de la base de données
0 2 * * * /usr/bin/sqlite3 /home/nova/NOVA-SERVER/data/supplier_tariffs.db ".backup '/home/nova/backups/supplier_tariffs_$(date +\%Y\%m\%d).db'"
```

---

## 📝 Checklist Déploiement

- [ ] DNS configuré et propagé
- [ ] Nginx installé et démarré
- [ ] Certificat SSL obtenu (Let's Encrypt)
- [ ] Configuration Nginx copiée et activée
- [ ] Backend NOVA configuré (`.env`)
- [ ] Service systemd créé et activé
- [ ] Backend démarré et accessible
- [ ] Tests : `curl http://127.0.0.1:8000/health`
- [ ] Tests : `https://nova-rondot.itspirit.ovh/`
- [ ] Logs vérifiés (pas d'erreurs)
- [ ] Pare-feu configuré (UFW)
- [ ] Monitoring en place
- [ ] Sauvegardes configurées

---

## 🆘 Support

En cas de problème :

1. **Vérifier les logs** : Nginx + NOVA Backend
2. **Tester le backend** : `curl http://127.0.0.1:8000/health`
3. **Vérifier Nginx** : `sudo nginx -t`
4. **Vérifier le service** : `sudo systemctl status nova-server`

---

## 📚 Références

- [Nginx Documentation](https://nginx.org/en/docs/)
- [Let's Encrypt Certbot](https://certbot.eff.org/)
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)
- [NOVA-SERVER README](../README.md)
