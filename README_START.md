# Démarrage et Déploiement NOVA-SERVER

## Architecture serveur

Ce Windows Server héberge **deux applications Python** indépendantes :

| Application | Exécutable | Port | Rôle |
| ----------- | ---------- | ---- | ---- |
| **NOVA** | `.venv\Scripts\python.exe main.py` | **8001** | Mail-to-Biz, IA, SAP |
| **BIOFORCE** | `C:\Python\python.exe main.py` | **8000** | Application Bioforce |

Le domaine `nova-rondot.itspirit.ovh` pointe vers ce serveur et est redirigé vers NOVA (port 8001).

> **ATTENTION** : Ne jamais tuer tous les processus `python.exe` — cela arrêterait aussi BIOFORCE.

---

## Démarrage NOVA

```cmd
cd C:\Users\PPZ\NOVA-SERVER
.venv\Scripts\python.exe main.py
```

## Redémarrage NOVA (sans toucher BIOFORCE)

Utiliser le script corrigé :

```cmd
restart_server.bat
```

Ce script identifie uniquement le PID NOVA (chemin `.venv\Scripts\python.exe`) avant de le tuer.

---

## URLs d'accès

| Service | URL |
| ------- | --- |
| Mail-to-Biz | <http://localhost:8001/mail-to-biz> |
| NOVA Assistant | <http://localhost:8001/interface/itspirit> |
| Documentation API | <http://localhost:8001/docs> |
| Health Check | <http://localhost:8001/health> |
| Frontend dev (Vite) | <http://localhost:8082/mail-to-biz/> |

---

## Développement frontend (mail-to-biz)

### Mode développement (hot-reload)

```cmd
cd mail-to-biz
npm run dev
```

Accessible sur `http://localhost:8082/mail-to-biz/`

Le proxy Vite redirige automatiquement les appels `/api/*` vers `localhost:8001`.

### Build et mise en production

```cmd
cd mail-to-biz
npm run build
```

Le build est **directement écrit dans `../frontend/`** (configuré dans `vite.config.ts`).
FastAPI sert `frontend/` sur `/mail-to-biz` — la mise en ligne est **immédiate**, aucune copie manuelle nécessaire.

---

## Dépannage

### Vérifier quel Python tourne sur quel port

```cmd
wmic process where "name='python.exe'" get ProcessId,ExecutablePath,CommandLine
```

### Routes FastAPI qui ne répondent pas

Si une route retourne une erreur inattendue après modification de code Python :

1. Vérifier que le serveur a bien été redémarré (le code Python est chargé au démarrage)
2. Supprimer les `.pyc` stale si nécessaire : `del routes\__pycache__\*.pyc`
3. Redémarrer via `restart_server.bat`

### Logs

Les logs uvicorn s'affichent dans la fenêtre de console du serveur NOVA.
