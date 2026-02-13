# Déploiement NOVA sur Windows Server 2019 + Cloudflare

## 🎯 Architecture

```
Internet → Cloudflare (CDN/Proxy) → Windows Server 2019 → NOVA Backend (localhost:8001)
```

**Cloudflare gère :**
- SSL/TLS (certificat automatique)
- CDN / Cache
- Protection DDoS
- Compression

**Windows Server gère :**
- Backend NOVA (FastAPI sur port 8000)

---

## 📋 Prérequis

- ✅ Windows Server 2019
- ✅ Python 3.9+ installé
- ✅ Compte Cloudflare (gratuit ou payant)
- ✅ Domaine `itspirit.ovh` configuré sur Cloudflare

---

## 🚀 Solution 1 : Cloudflare Direct (Recommandé)

### Configuration la plus simple sans reverse proxy local

### Étape 1 : Configurer NOVA pour écouter sur le réseau

**Fichier `.env` :**
```env
# Mode production
NOVA_MODE=production

# Écoute sur toutes les interfaces (nécessaire pour Cloudflare)
APP_HOST=0.0.0.0
APP_PORT=8000

# Désactiver reload
UVICORN_RELOAD=false
```

### Étape 2 : Ouvrir le port dans le pare-feu Windows

**PowerShell (Administrateur) :**
```powershell
# Autoriser le port 8000
New-NetFirewallRule -DisplayName "NOVA Backend" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow

# Vérifier la règle
Get-NetFirewallRule -DisplayName "NOVA Backend"
```

### Étape 3 : Démarrer NOVA en service Windows

Voir [Service Windows](#service-windows) ci-dessous.

### Étape 4 : Configurer Cloudflare DNS

**Dans le dashboard Cloudflare (itspirit.ovh) :**

| Type | Nom | Contenu | Proxy | TTL |
|------|-----|---------|-------|-----|
| A | nova-rondot | `<IP_PUBLIQUE_SERVEUR>` | ✅ Proxied (Orange) | Auto |

**Important :** Activer le mode **Proxied** (icône orange) pour bénéficier de Cloudflare.

### Étape 5 : Configurer les règles Cloudflare

#### 5.1 - Configuration SSL/TLS

**Dashboard Cloudflare → SSL/TLS → Overview**

Mode SSL/TLS : **Full** (pas Strict car pas de certificat local requis)

#### 5.2 - Page Rules (Redirection root)

**Dashboard Cloudflare → Rules → Page Rules**

**Règle 1 : Rediriger la racine vers /mail-to-biz**
```
URL : https://nova-rondot.itspirit.ovh/
Setting : Forwarding URL (301 - Permanent Redirect)
Destination : https://nova-rondot.itspirit.ovh/mail-to-biz
```

**Règle 2 : Désactiver cache pour l'API**
```
URL : https://nova-rondot.itspirit.ovh/api/*
Settings :
  - Cache Level: Bypass
  - Disable Performance
```

**Règle 3 : Cache agressif pour les assets**
```
URL : https://nova-rondot.itspirit.ovh/mail-to-biz/assets/*
Settings :
  - Cache Level: Cache Everything
  - Edge Cache TTL: 1 day
```

#### 5.3 - Transform Rules (Optionnel)

Si vous voulez que `https://nova-rondot.itspirit.ovh/` serve directement `/mail-to-biz` sans changer l'URL :

**Dashboard Cloudflare → Rules → Transform Rules → URL Rewrite**

```
Rule name : Rewrite root to mail-to-biz
When incoming requests match :
  - Hostname equals nova-rondot.itspirit.ovh
  - URI Path equals /

Then :
  - Rewrite to : /mail-to-biz
```

### Étape 6 : Tester

```powershell
# Test local
curl http://localhost:8001/health

# Test via Cloudflare
curl https://nova-rondot.itspirit.ovh/health
```

---

## 🚀 Solution 2 : Cloudflare Tunnel (Plus sécurisé)

### Avantages
- ✅ Pas besoin d'ouvrir de port dans le pare-feu
- ✅ Connexion chiffrée de bout en bout
- ✅ IP du serveur cachée
- ✅ Gratuit

### Étape 1 : Installer cloudflared

**Télécharger cloudflared pour Windows :**
```
https://github.com/cloudflare/cloudflared/releases/latest
```

Télécharger : `cloudflared-windows-amd64.exe`

**Installer dans `C:\Program Files\cloudflared\` :**
```powershell
# Créer le dossier
New-Item -ItemType Directory -Force -Path "C:\Program Files\cloudflared"

# Copier l'exécutable
Move-Item cloudflared-windows-amd64.exe "C:\Program Files\cloudflared\cloudflared.exe"

# Ajouter au PATH
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\Program Files\cloudflared", [EnvironmentVariableTarget]::Machine)
```

### Étape 2 : Authentifier cloudflared

```powershell
cloudflared tunnel login
```

Une page web s'ouvre → Sélectionner le domaine `itspirit.ovh`

### Étape 3 : Créer un tunnel

```powershell
cloudflared tunnel create nova-tunnel
```

**Note l'UUID du tunnel affiché :**
```
Tunnel credentials written to C:\Users\<USER>\.cloudflared\<UUID>.json
```

### Étape 4 : Configurer le tunnel

**Créer le fichier : `C:\Users\<USER>\.cloudflared\config.yml`**

```yaml
tunnel: <UUID_DU_TUNNEL>
credentials-file: C:\Users\<USER>\.cloudflared\<UUID>.json

ingress:
  # Rediriger nova-rondot.itspirit.ovh vers le backend local
  - hostname: nova-rondot.itspirit.ovh
    service: http://localhost:8001

  # Catch-all (obligatoire)
  - service: http_status:404
```

### Étape 5 : Router le DNS via le tunnel

```powershell
cloudflared tunnel route dns nova-tunnel nova-rondot.itspirit.ovh
```

Cela crée automatiquement l'enregistrement DNS dans Cloudflare.

### Étape 6 : Démarrer le tunnel

**Test :**
```powershell
cloudflared tunnel run nova-tunnel
```

**Installer comme service Windows :**
```powershell
cloudflared service install
```

**Démarrer le service :**
```powershell
Start-Service cloudflared
```

### Étape 7 : Configuration NOVA

**Avec Cloudflare Tunnel, NOVA peut rester en local :**

```env
APP_HOST=127.0.0.1
APP_PORT=8000
```

**Pas besoin d'ouvrir de port dans le pare-feu !**

### Étape 8 : Tester

```
https://nova-rondot.itspirit.ovh/health
```

---

## 🔧 Service Windows pour NOVA

### Option A : NSSM (Recommandé)

**1. Télécharger NSSM :**
```
https://nssm.cc/download
```

**2. Installer NSSM :**
```powershell
# Extraire dans C:\nssm
# Ajouter au PATH
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\nssm\win64", [EnvironmentVariableTarget]::Machine)
```

**3. Créer le service :**
```powershell
nssm install NOVA-Backend "C:\Users\PPZ\NOVA-SERVER\.venv\Scripts\python.exe" "C:\Users\PPZ\NOVA-SERVER\main.py"

# Configurer le working directory
nssm set NOVA-Backend AppDirectory "C:\Users\PPZ\NOVA-SERVER"

# Configurer les logs
nssm set NOVA-Backend AppStdout "C:\Users\PPZ\NOVA-SERVER\logs\service.log"
nssm set NOVA-Backend AppStderr "C:\Users\PPZ\NOVA-SERVER\logs\service-error.log"

# Démarrage automatique
nssm set NOVA-Backend Start SERVICE_AUTO_START

# Démarrer le service
nssm start NOVA-Backend
```

**4. Gérer le service :**
```powershell
# Statut
nssm status NOVA-Backend

# Arrêter
nssm stop NOVA-Backend

# Redémarrer
nssm restart NOVA-Backend

# Supprimer
nssm remove NOVA-Backend confirm
```

### Option B : Task Scheduler

**1. Créer une tâche planifiée :**

```powershell
# Script PowerShell : start-nova-service.ps1
$action = New-ScheduledTaskAction -Execute "C:\Users\PPZ\NOVA-SERVER\.venv\Scripts\python.exe" -Argument "C:\Users\PPZ\NOVA-SERVER\main.py" -WorkingDirectory "C:\Users\PPZ\NOVA-SERVER"

$trigger = New-ScheduledTaskTrigger -AtStartup

$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName "NOVA-Backend" -Action $action -Trigger $trigger -Principal $principal -Settings $settings
```

**2. Démarrer la tâche :**
```powershell
Start-ScheduledTask -TaskName "NOVA-Backend"
```

### Option C : Script PowerShell au démarrage

**Créer : `C:\Users\PPZ\NOVA-SERVER\start-service.ps1`**

```powershell
# Aller dans le dossier NOVA
Set-Location "C:\Users\PPZ\NOVA-SERVER"

# Activer l'environnement virtuel
& ".\.venv\Scripts\Activate.ps1"

# Démarrer le serveur (boucle infinie)
while ($true) {
    try {
        python main.py
    } catch {
        Write-Host "NOVA crashed. Restarting in 5 seconds..."
        Start-Sleep -Seconds 5
    }
}
```

**Ajouter au démarrage :**
- `Win + R` → `shell:startup`
- Créer un raccourci vers le script PowerShell

---

## 📊 Configuration Cloudflare Optimale

### 1. SSL/TLS Settings

**Dashboard → SSL/TLS**

| Setting | Value |
|---------|-------|
| Mode | Full |
| Always Use HTTPS | ✅ On |
| Automatic HTTPS Rewrites | ✅ On |
| Minimum TLS Version | 1.2 |

### 2. Speed Settings

**Dashboard → Speed → Optimization**

| Setting | Value |
|---------|-------|
| Auto Minify | ✅ JavaScript, ✅ CSS, ✅ HTML |
| Brotli | ✅ On |
| Early Hints | ✅ On |
| HTTP/2 to Origin | ✅ On |
| HTTP/3 (with QUIC) | ✅ On |

### 3. Caching

**Dashboard → Caching → Configuration**

| Setting | Value |
|---------|-------|
| Caching Level | Standard |
| Browser Cache TTL | 4 hours |
| Always Online | ✅ On |

### 4. Firewall Rules (Optionnel)

**Dashboard → Security → WAF**

Activer le WAF pour protection automatique contre :
- SQL Injection
- XSS
- OWASP Top 10

---

## 🔐 Sécurité

### 1. Restreindre l'accès au backend

Si vous utilisez **Solution 1** (Direct), restreindre l'accès aux IPs Cloudflare uniquement :

**PowerShell (Administrateur) :**
```powershell
# Supprimer la règle précédente
Remove-NetFirewallRule -DisplayName "NOVA Backend"

# Liste IPs Cloudflare : https://www.cloudflare.com/ips/
# Créer une règle pour chaque plage IP Cloudflare
$cloudflareIPs = @(
    "173.245.48.0/20",
    "103.21.244.0/22",
    "103.22.200.0/22",
    # ... (voir liste complète sur cloudflare.com/ips/)
)

foreach ($ip in $cloudflareIPs) {
    New-NetFirewallRule -DisplayName "NOVA Backend - Cloudflare $ip" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow -RemoteAddress $ip
}
```

### 2. Variables d'environnement sensibles

Stocker les secrets dans des variables d'environnement Windows :

```powershell
[Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-...", [EnvironmentVariableTarget]::Machine)
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "sk-proj-...", [EnvironmentVariableTarget]::Machine)
```

---

## 🧪 Tests

### Test Backend Local
```powershell
Invoke-WebRequest -Uri http://localhost:8001/health
```

### Test via Cloudflare
```powershell
Invoke-WebRequest -Uri https://nova-rondot.itspirit.ovh/health
```

### Test Redirection Root
```powershell
Invoke-WebRequest -Uri https://nova-rondot.itspirit.ovh/ -MaximumRedirection 0
# Doit retourner 301/302
```

---

## 📋 Checklist Déploiement

- [ ] Python 3.9+ installé sur Windows Server
- [ ] NOVA Backend démarré localement (port 8000)
- [ ] Domaine `nova-rondot.itspirit.ovh` ajouté à Cloudflare
- [ ] DNS configuré (A record → IP serveur)
- [ ] SSL/TLS configuré sur Cloudflare (Mode: Full)
- [ ] Page Rules créées (redirection root)
- [ ] Service Windows configuré (NSSM ou Task Scheduler)
- [ ] Pare-feu configuré (port 8000 ou Tunnel)
- [ ] Tests réussis (local + Cloudflare)

---

## 🆘 Dépannage

### Problème : 521 Error (Web Server Is Down)

**Cause :** Cloudflare ne peut pas joindre le backend

**Solution :**
1. Vérifier que NOVA est démarré : `curl http://localhost:8001/health`
2. Vérifier le pare-feu Windows
3. Vérifier que `APP_HOST=0.0.0.0` dans `.env`
4. Vérifier les logs : `C:\Users\PPZ\NOVA-SERVER\nova.log`

### Problème : 522 Error (Connection Timed Out)

**Cause :** Timeout de connexion

**Solution :**
1. Augmenter les timeouts dans Cloudflare (Enterprise uniquement)
2. Optimiser les requêtes longues dans NOVA
3. Utiliser WebSocket pour les opérations longues

### Problème : Boucle de redirection infinie

**Cause :** Configuration SSL/TLS incorrecte

**Solution :**
1. Cloudflare → SSL/TLS → Mode : **Full** (pas Flexible)
2. Backend NOVA doit écouter en HTTP (pas HTTPS)

---

## 📚 Références

- [Cloudflare Tunnel Documentation](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
- [Cloudflare Page Rules](https://developers.cloudflare.com/rules/page-rules/)
- [NSSM Documentation](https://nssm.cc/usage)
- [Cloudflare IP Ranges](https://www.cloudflare.com/ips/)

---

## 🎉 Architecture Finale

```
┌─────────────────────────────────────────────────────────┐
│                      Internet                            │
└────────────────────────┬────────────────────────────────┘
                         │
                         │ HTTPS (443)
                         ▼
┌─────────────────────────────────────────────────────────┐
│              Cloudflare (CDN/Proxy)                      │
│  - SSL/TLS automatique                                   │
│  - Cache / CDN                                           │
│  - Protection DDoS                                       │
│  - Compression                                           │
│  - Page Rules (redirection root → /mail-to-biz)         │
└────────────────────────┬────────────────────────────────┘
                         │
                         │ HTTP (8000) ou Tunnel
                         ▼
┌─────────────────────────────────────────────────────────┐
│           Windows Server 2019                            │
│                                                           │
│  ┌──────────────────────────────────────────────────┐   │
│  │  NOVA Backend (FastAPI)                          │   │
│  │  - Port: 8000                                    │   │
│  │  - Service Windows (NSSM)                        │   │
│  │  - /mail-to-biz (React SPA)                      │   │
│  │  - /api (REST API)                               │   │
│  │  - /ws (WebSocket)                               │   │
│  └──────────────────────────────────────────────────┘   │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

**Résultat :**
- `https://nova-rondot.itspirit.ovh/` → Redirige vers `/mail-to-biz`
- SSL géré par Cloudflare (gratuit, automatique)
- Backend protégé, seulement accessible via Cloudflare
