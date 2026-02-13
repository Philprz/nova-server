# Scripts de Démarrage NOVA-SERVER

## 📦 Scripts Disponibles

NOVA-SERVER dispose de **3 scripts de démarrage** pour lancer facilement le backend et le frontend :

| Script | Plateforme | Description |
|--------|-----------|-------------|
| `start-nova.bat` | Windows | Script batch Windows |
| `start-nova.sh` | Linux/Mac | Script shell Bash |
| `start-nova.py` | Tous | Script Python universel (recommandé) |

---

## 🚀 Utilisation

### Windows

**Méthode 1 : Double-clic**
```
Double-cliquer sur start-nova.bat
```

**Méthode 2 : Terminal**
```cmd
start-nova.bat
```

**Méthode 3 : Python (recommandé)**
```cmd
python start-nova.py
```

### Linux / Mac

**Méthode 1 : Script Bash**
```bash
chmod +x start-nova.sh
./start-nova.sh
```

**Méthode 2 : Python (recommandé)**
```bash
python3 start-nova.py
```

---

## 🔧 Fonctionnement

### 1. Démarrage Backend (FastAPI)

Le script démarre automatiquement le serveur FastAPI sur **http://localhost:8001**

### 2. Démarrage Frontend (Optionnel)

Si **Node.js** est installé ET que le dossier `mail-to-biz/src/` existe :
- Le script démarre le **React Dev Server** sur **http://localhost:5173**

Sinon :
- Le frontend **compilé** est servi par FastAPI sur **/mail-to-biz**

---

## 📍 URLs d'Accès

Une fois NOVA démarré, vous pouvez accéder à :

| Service | URL | Description |
|---------|-----|-------------|
| **Backend API** | http://localhost:8001 | API REST FastAPI |
| **Mail-to-Biz** | http://localhost:8001/mail-to-biz | Interface mail-to-biz (React) |
| **NOVA Assistant** | http://localhost:8001/interface/itspirit | Assistant IA conversationnel |
| **Documentation API** | http://localhost:8001/docs | Swagger UI interactive |
| **Health Check** | http://localhost:8001/health | Statut système |
| **Frontend Dev** | http://localhost:5173 | React Dev Server (si actif) |

---

## 🛑 Arrêt

### Windows
- Appuyer sur **une touche** dans la fenêtre du script
- Ou fermer les fenêtres de console

### Linux / Mac / Python
- Appuyer sur **CTRL+C** dans le terminal

Les processus sont arrêtés proprement.

---

## ⚙️ Configuration

### Ports par Défaut

- **Backend** : 8000 (configurable dans `.env` : `APP_PORT`)
- **Frontend Dev** : 5173 (configurable dans `mail-to-biz/vite.config.ts`)

### Variables d'Environnement

Le backend utilise le fichier `.env` pour sa configuration.

Voir [README.md](README.md) pour la liste complète des variables.

---

## 🐛 Dépannage

### Problème : "Port déjà utilisé"

Les scripts tuent automatiquement les processus existants sur les ports 8000 et 5173.

Si le problème persiste :

**Windows :**
```cmd
netstat -ano | findstr :8000
taskkill /F /PID <PID>
```

**Linux/Mac :**
```bash
lsof -ti:8000 | xargs kill -9
```

### Problème : "Python non trouvé"

Installer Python 3.9+ depuis https://www.python.org/downloads/

### Problème : "Node.js non trouvé"

Le frontend **compilé** sera servi par FastAPI (pas besoin de Node.js en production).

Pour développement frontend, installer Node.js : https://nodejs.org/

---

## 📊 Logs

### Backend

Les logs FastAPI sont affichés dans la console :
- Fichier : `nova.log`
- Format : `YYYY-MM-DD HH:MM:SS - module - LEVEL - message`

### Frontend Dev

Les logs Vite/React sont affichés dans la console du frontend.

---

## 🔄 Workflow Développement

### 1. Développement Backend uniquement

```bash
python main.py
```

### 2. Développement Frontend uniquement

```bash
cd mail-to-biz
npm run dev
```

### 3. Développement Full-Stack

```bash
# Windows
start-nova.bat

# Linux/Mac
./start-nova.sh

# Universel
python start-nova.py
```

---

## 📚 Documentation Technique

### start-nova.py (Recommandé)

**Avantages :**
- ✅ Multiplateforme (Windows, Linux, Mac)
- ✅ Gestion propre des processus
- ✅ Vérifications préalables (Python, Node.js)
- ✅ Libération automatique des ports
- ✅ Arrêt propre avec CTRL+C
- ✅ Affichage couleurs dans terminal

**Fonctionnalités :**
```python
# Vérifications
check_python()      # Python 3.9+
check_node()        # Node.js installé
check_frontend_source()  # mail-to-biz/src/ existe

# Démarrage
start_backend()     # FastAPI sur port 8000
start_frontend()    # React Dev sur port 5173 (optionnel)

# Nettoyage
cleanup()           # Arrêt propre des processus
```

### start-nova.bat (Windows)

Script batch natif Windows avec gestion des fenêtres séparées.

### start-nova.sh (Linux/Mac)

Script shell Bash avec gestion des signaux SIGINT/SIGTERM.

---

## 🎯 Cas d'Usage

### Production

```bash
# Backend uniquement (frontend compilé servi par FastAPI)
python main.py
```

Le frontend est déjà compilé dans `frontend/` et servi par FastAPI.

### Développement

```bash
# Full-stack avec hot-reload
python start-nova.py
```

- Backend : Hot-reload uvicorn
- Frontend : Hot-reload Vite

### CI/CD

```bash
# Build frontend
cd mail-to-biz
npm run build
cp -r dist/* ../frontend/

# Démarrage production
cd ..
python main.py
```

---

## 🔐 Sécurité

### Production

- Modifier `APP_HOST` dans `.env` : `APP_HOST=127.0.0.1` (local uniquement)
- Utiliser un reverse proxy (Nginx, Caddy)
- Activer HTTPS
- Configurer CORS restrictif

### Développement

- `APP_HOST=0.0.0.0` permet l'accès réseau local
- Utile pour tester sur mobile/tablette

---

## 📝 Version

**Scripts v1.0.0** (09/02/2026)
- Démarrage unifié backend + frontend
- Support Windows, Linux, Mac
- Gestion propre des processus
- Libération automatique des ports

---

## 🆘 Support

Pour toute question ou problème :
1. Vérifier les logs : `nova.log`
2. Vérifier le health check : http://localhost:8001/health
3. Consulter la documentation : http://localhost:8001/docs
