# NOVA Middleware - Claude + Salesforce + SAP B1

**NOVA Middleware** est une passerelle **FastAPI + MCP** permettant d'interfacer :
- 🧠 Claude (LLM via MCP)
- ☁️ Salesforce (SOQL API)
- 🏭 SAP Business One (REST API)
- 🗃 PostgreSQL (stockage interne)

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
├── main.py                     # Entrée FastAPI (port 8000)
├── server_mcp.py               # Serveur MCP principal (stdio)
├── salesforce_mcp.py           # Serveur MCP Salesforce (stdio)
├── start_nova_improved.ps1     # Script de démarrage automatisé
├── db/
│   ├── models.py               # Modèles SQLAlchemy
│   └── session.py              # Connexion DB / get_db()
├── routes/                     # Endpoints CRUD FastAPI
├── tools.py                    # Outils métiers exposés à Claude
├── services/
│   ├── exploration_sap.py      # Inspection SAP
│   ├── exploration_salesforce.py # Inspection Salesforce
│   ├── sap.py                  # Connecteur SAP
│   └── salesforce.py           # Connecteur Salesforce
├── mcp_app.py                  # FastMCP instance
├── .env                        # Secrets (Salesforce, DB, API)
├── postman/                    # Collections pour tests API
└── README.md                   # Documentation
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

Créez un fichier `.env` avec les informations suivantes :
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

Configurer PostgreSQL :
```sql
CREATE DATABASE nova_mcp WITH OWNER = nova_user ENCODING = 'UTF8';
CREATE USER nova_user WITH ENCRYPTED PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE nova_mcp TO nova_user;
```

Configurer Alembic :
```bash
alembic revision --autogenerate -m "Initial schema"
alembic upgrade head
```

---

## 🚀 Démarrage rapide

Le moyen le plus simple de démarrer tous les services est d'utiliser le script PowerShell automatisé :

```powershell
# Pour démarrer uniquement FastAPI
.\start_nova_improved.ps1

# Pour démarrer FastAPI et les serveurs MCP
.\start_nova_improved.ps1 -MCP

# Pour tout démarrer (FastAPI, MCP, Claude Desktop si installé)
.\start_nova_improved.ps1 -All
```

Ce script :
- Active l'environnement virtuel
- Démarre le serveur FastAPI
- Vérifie la connexion Salesforce
- Démarre les serveurs MCP (avec l'option `-MCP` ou `-All`)
- Configure et lance Claude Desktop (avec l'option `-All`)

## 🧠 Démarrer Claude MCP manuellement

Si vous préférez démarrer les services manuellement :

```bash
# Dans un premier terminal
.\venv\Scripts\Activate.ps1
python server_mcp.py

# Dans un deuxième terminal
.\venv\Scripts\Activate.ps1
python salesforce_mcp.py

# Installer les MCP dans Claude Desktop
python -m mcp install server_mcp.py --name nova_middleware -f .env
python -m mcp install salesforce_mcp.py --name salesforce_mcp -f .env
```

---

## 🔌 API REST (FastAPI)

Démarrer le serveur manuellement :
```bash
.\venv\Scripts\Activate.ps1
uvicorn main:app --reload
```

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

| Nom | Description |
|-----|-------------|
| `ping` | Test simple de disponibilité |
| `echo` | Renvoie le message reçu |
| `env_check` | Vérifie la configuration |
| `sap.read` | Lecture d'un endpoint SAP |
| `salesforce.query` | Exécute une requête SOQL |
| `sap.inspect` | Liste les endpoints SAP (via metadata) |
| `salesforce.inspect` | Liste des objets Salesforce |

Exemples d'utilisation dans Claude Desktop :
```
# Test de base
ping

# Requête Salesforce
salesforce.query("SELECT Id, Name FROM Account LIMIT 5")

# Inspection des objets Salesforce
salesforce.inspect()
salesforce.inspect("Account")

# Lecture SAP
sap.read("/Items", "GET")
```

---

## 🔍 Test et débogage

### Test de connexion Salesforce
```powershell
.\venv\Scripts\Activate.ps1
python test_salesforce_connection.py
```

### Test des endpoints FastAPI avec Postman
Importez les collections de test depuis le dossier `postman/` :
- `nova_tests.postman_collection.json`
- `NOVA_Middleware_CRUD.postman_collection.json`
- `NOVA_Server_Test.json`
- `Exploration_MCP.postman_collection.json`

### Test WebSocket MCP
```powershell
.\venv\Scripts\Activate.ps1
python test_mcp_ws.py
```

---

## 📈 Backlog

- 🔲 Prompts Claude (via `prompts.yaml`)
- 🔲 `salesforce.populate` pour créer 10 comptes test
- 🔲 Ajout `updated_at` sur tous les modèles
- 🔲 Stats API `/stats` (tickets par client, etc.)
- 🔲 Front React (si version publique souhaitée)
- 🔲 Intégration avec Jira, Zendesk et Confluence

---

## 🪲 Résolution des problèmes courants

### Problèmes d'encodage dans la console PowerShell
Si vous rencontrez des problèmes d'affichage des caractères spéciaux :
```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
```

### Erreur ModuleNotFoundError
Si vous obtenez une erreur "No module named 'fastapi'" ou similaire :
```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Erreur de connexion SAP
Vérifiez que le serveur SAP est accessible et que vos identifiants sont corrects :
```powershell
.\venv\Scripts\Activate.ps1
python -c "from services.sap import login_sap; import asyncio; asyncio.run(login_sap())"
```

### Erreur MCP "Access Denied"
Assurez-vous que le fichier `.env` est accessible et contient les bonnes variables :
```powershell
python -m mcp install server_mcp.py --name nova_middleware -f .env --force
```

---

© 2025 IT Spirit – Projet NOVA Middleware