# Configuration Caddy pour NOVA mail-to-biz

## Installation de Caddy

Si Caddy n'est pas installé :

### Windows
```bash
# Via Chocolatey
choco install caddy

# Ou télécharger depuis https://caddyserver.com/download
```

### Linux
```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy
```

## Utilisation

### 1. Démarrer le serveur NOVA (FastAPI)
```bash
python main.py
```
Le serveur écoute sur `http://localhost:8000`

### 2. Démarrer Caddy (reverse proxy)

**Windows :**
```bash
start-caddy.bat
```

**Linux/Mac :**
```bash
caddy run --config Caddyfile
```

### 3. Accéder à l'application

- **Interface mail-to-biz** : http://localhost/ (routé vers `/mail-to-biz`)
- **API directe** : http://localhost:8000/
- **Documentation** : http://localhost/docs
- **Health check** : http://localhost/health

## Configuration pour production

1. Éditer `Caddyfile`
2. Décommenter la section `nova.itspirit.ovh`
3. Adapter le domaine si nécessaire
4. Redémarrer Caddy :
   ```bash
   sudo systemctl reload caddy
   ```

## Architecture

```
Internet (https://nova.itspirit.ovh)
    ↓
Caddy (port 80/443)
    ↓ rewrite / → /mail-to-biz
FastAPI NOVA (port 8000)
    ↓
SAP B1 Rondot API
```

## Notes

- Caddy gère automatiquement les certificats SSL en production
- Le rewrite est transparent pour l'utilisateur
- Les APIs restent accessibles sur `/api/*`
- La documentation reste sur `/docs`
