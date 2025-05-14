# NOVA Middleware - Claude + Salesforce + SAP B1

**NOVA Middleware** est une passerelle permettant d'intégrer:
- 🧠 Claude (LLM via MCP)
- ☁️ Salesforce (SOQL API)
- 🏭 SAP Business One (REST API)
- 🗃️ PostgreSQL (stockage interne)

---

## 🚀 Mise à jour du 13 mai 2025

### Nouveautés

- ✅ Implémentation MCP (Model Context Protocol) pour intégration avec Claude 3.7
- ✅ Création de serveurs MCP minimalistes fonctionnels
- ✅ Correction des problèmes d'encodage sur Windows
- ✅ Structure de déploiement optimisée
- ✅ Documentation des procédures de démarrage

### Problèmes résolus

- ✓ Correction des erreurs `No module named 'simple_salesforce'`
- ✓ Résolution des problèmes d'encodage (`charmap codec can't encode character`)
- ✓ Configuration correcte pour Claude Desktop
- ✓ Journalisation améliorée pour le débogage

---

## 🔧 Prérequis

- Windows Server 2019+ (x64)
- Python 3.10+
- PostgreSQL >= 15 (UTF8)
- Claude Desktop installé (MCP compatible)
- Variables d'environnement dans `.env`

---

## 📦 Structure du projet

```
NOVA/
├── main.py                      # Entrée FastAPI (port 8000)
├── server_mcp.py                # Serveur MCP principal
├── salesforce_mcp_minimal.py    # Serveur MCP Salesforce (version stable)
├── sap_mcp_minimal.py           # Serveur MCP SAP (version stable)
├── start_nova_simple.ps1        # Script de démarrage automatisé
├── db/
│   ├── models.py                # Modèles SQLAlchemy
│   └── session.py               # Connexion DB / get_db()
├── routes/                      # Endpoints CRUD FastAPI
├── services/
│   ├── exploration_sap.py       # Inspection SAP
│   ├── exploration_salesforce.py # Inspection Salesforce
│   ├── sap.py                   # Connecteur SAP
│   └── salesforce.py            # Connecteur Salesforce
├── logs/                        # Répertoire pour les logs MCP
├── .env                         # Secrets (Salesforce, DB, API)
└── README.md                    # Documentation
```

---

## ⚙️ Installation

```bash
git clone <repo> NOVA
cd NOVA
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

#### Mise à jour des dépendances

Si vous migrez depuis une version antérieure ou rencontrez des problèmes :

```bash
.\venv\Scripts\Activate.ps1
pip install simple-salesforce mcp httpx fastapi uvicorn python-dotenv --upgrade
```

#### Fichier `.env` requis

```
ANTHROPIC_API_KEY=sk-ant-api03-xxx
SALESFORCE_USERNAME=username@example.com
SALESFORCE_PASSWORD=yourpassword
SALESFORCE_SECURITY_TOKEN=securitytoken
SALESFORCE_DOMAIN=login

SAP_REST_BASE_URL=https://your-sap-server:50000/b1s/v1
SAP_USER=manager
SAP_CLIENT=SBODemoFR
SAP_CLIENT_PASSWORD=yourpassword

API_KEY=yourapikey

DATABASE_URL=postgresql://nova_user:password@localhost:5432/nova_mcp
```

---

## 🚀 Démarrage rapide

```powershell
# Démarrer tous les services (FastAPI + MCP)
.\start_nova_simple.ps1
```

Ce script :
- Active l'environnement virtuel
- Démarre le serveur FastAPI
- Démarre les serveurs MCP minimalistes
- Affiche les URLs et statuts des services

---

## 🧠 Configuration Claude Desktop

Pour intégrer les outils MCP avec Claude Desktop :

1. Créez ou mettez à jour le fichier dans `%APPDATA%\Claude\claude_desktop_config.json` :

```json
{
  "mcpServers": {
    "salesforce_mcp": {
      "command": "python",
      "args": ["C:\\Users\\PPZ\\NOVA\\salesforce_mcp_minimal.py"],
      "cwd": "C:\\Users\\PPZ\\NOVA",
      "envFile": ".env",
      "stdio": true
    },
    "sap_mcp": {
      "command": "python",
      "args": ["C:\\Users\\PPZ\\NOVA\\sap_mcp_minimal.py"],
      "cwd": "C:\\Users\\PPZ\\NOVA",
      "envFile": ".env",
      "stdio": true
    }
  }
}
```

2. Relancez Claude Desktop
3. Activez les outils via l'interface de Claude Desktop (bouton "+")

---

## 🔌 API REST (FastAPI)

Endpoints disponibles :
- `POST /clients`
- `GET /clients`
- `POST /utilisateurs`
- `POST /tickets`
- `POST /factures`
- `POST /interactions_llm`
- `POST /salesforce_query`
- `POST /sap_query`
- `GET /sap_login_test`

Documentation API interactive :
- Swagger UI : http://localhost:8000/docs
- ReDoc : http://localhost:8000/redoc

---

## 🧰 Outils Claude (MCP)

| Outil | Description |
|-------|-------------|
| `ping` | Test de disponibilité du serveur MCP |
| `salesforce.query` | Exécute une requête SOQL sur Salesforce |
| `salesforce.inspect` | Liste les objets et champs Salesforce |
| `sap.read` | Lit des données SAP via API REST |
| `sap.inspect` | Liste les endpoints SAP disponibles |

Exemples d'utilisation dans Claude Desktop :
```
# Test simple
ping

# Requête Salesforce
salesforce.query("SELECT Id, Name FROM Account LIMIT 5")

# Inspection d'un objet Salesforce
salesforce.inspect("Account")

# Lecture de données SAP
sap.read("/Items", "GET")
```

---

## 🪲 Résolution des problèmes courants

### Erreur MCP "No module named 'simple_salesforce'"

```powershell
.\venv\Scripts\Activate.ps1
pip install simple-salesforce
```

### Problèmes d'encodage (caractères spéciaux/emojis)

Assurez-vous que les fichiers MCP incluent ce code :

```python
# Configuration de l'encodage pour Windows
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
```

### Échecs de connexion Claude Desktop - MCP

1. Vérifiez les logs dans `logs/`
2. Assurez-vous que les chemins dans `claude_desktop_config.json` sont corrects
3. Relancez Claude Desktop
4. Utilisez des versions minimales des serveurs MCP

### Session SAP expirée

```python
# Rafraîchir manuellement la session SAP
sap.refresh_session()
```

---

## 📊 Journalisation et débogage

Les serveurs MCP écrivent des logs détaillés dans les fichiers :
- `logs/salesforce_debug.log`
- `logs/sap_debug.log`

Pour activer le mode debug avancé :

```python
# Ajouter en haut des fichiers MCP
import os
os.environ["MCP_DEBUG"] = "1"
os.environ["MCP_LOG_LEVEL"] = "DEBUG"
```

---

## 📈 Backlog et prochaines étapes

- 🔲 Enrichir les serveurs MCP minimaux avec toutes les fonctionnalités
- 🔲 Ajouter des tests unitaires pour chaque outil MCP
- 🔲 Intégrer Jira, Zendesk et Confluence via MCP
- 🔲 Mettre en place Qdrant pour l'intégration de documentation
- 🔲 Développer une interface utilisateur dans Salesforce
- 🔲 Automatiser le démarrage à l'aide de services Windows

---

## 📚 Documentation MCP

Les outils MCP (Model Context Protocol) permettent à Claude d'exécuter du code Python en réponse à des prompts sans intervention manuelle. Pour approfondir vos connaissances sur MCP, consultez :

- [Documentation officielle MCP](https://modelcontextprotocol.io/docs/)
- [GitHub du projet MCP](https://github.com/anthropics/anthropic-tools)
- [Exemples de serveurs MCP](https://github.com/anthropics/anthropic-tools/tree/main/examples)

---

© 2025 IT Spirit – Projet NOVA Middleware