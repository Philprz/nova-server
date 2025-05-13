
# NOVA Middleware - Claude + Salesforce + SAP B1

**NOVA Middleware** est une passerelle **FastAPI + MCP** permettant d'interfacer :
- 🧠 Claude (LLM via MCP)
- ☁️ Salesforce (SOQL API)
- 🏭 SAP Business One (REST API)
- 🗃 PostgreSQL (stockage interne)

---

## 🔧 Prérequis

- Windows Server 2019 (x64)
- Python 3.10
- PostgreSQL >= 15 (UTF8)
- RabbitMQ + Erlang (facultatif pour worker)
- Claude Desktop installé (MCP compatible)
- Variables d'environnement dans `.env`

---

## 📦 Structure du projet

```
NOVA/
├── main.py                     # Entrée FastAPI (port 8000)
├── server_mcp.py               # Serveur Claude MCP (stdio)
├── db/
│   ├── models.py               # Modèles SQLAlchemy
│   └── session.py              # Connexion DB / get_db()
├── routes/                     # Endpoints CRUD FastAPI
├── tools.py                    # Outils métiers exposés à Claude
├── exploration_sap.py          # Inspection SAP
├── exploration_salesforce.py   # Inspection Salesforce
├── mcp_app.py                  # FastMCP instance
├── .env                        # Secrets (Salesforce, DB, API)
├── test_crud.http              # Tests API REST (VS Code)
├── NOVA_Middleware_CRUD.postman_collection.json
└── README.md                   # Ce fichier
```

---

## ⚙️ Installation

```bash
git clone <repo> NOVA
cd NOVA
python -m venv venv
.env\Scripts\Activate.ps1
pip install -r requirements.txt
```

Configurer PostgreSQL :
```sql
CREATE DATABASE nova_mcp WITH OWNER = nova_user ENCODING = 'UTF8';
CREATE USER nova_user WITH ENCRYPTED PASSWORD 'votre_mdpp';
GRANT ALL PRIVILEGES ON DATABASE nova_mcp TO nova_user;
```

Configurer Alembic :
```bash
alembic revision --autogenerate -m "Initial schema"
alembic upgrade head
```

---

## 🧠 Démarrer Claude MCP

```bash
.env\Scripts\mcp.exe dev server_mcp.py --with-editable .
```
Puis dans un 2e terminal :

```bash
.env\Scripts\mcp.exe install server_mcp.py --name nova_middleware -f .env
```

Ensuite, redémarrer **Claude Desktop**, cliquer sur ➕ → **nova_middleware**.

---

## 🔌 API REST (FastAPI)

Démarrer le serveur :
```bash
uvicorn main:app --reload
```

Endpoints disponibles :
- `POST /clients`
- `GET /clients`
- `POST /utilisateurs`
- `POST /tickets`
- `POST /factures`
- `POST /interactions_llm`

Fichiers de test :
- [`test_crud.http`](./test_crud.http)
- [`NOVA_Middleware_CRUD.postman_collection.json`](./NOVA_Middleware_CRUD.postman_collection.json)

---

## 🧰 Outils Claude (MCP)

| Nom | Description |
|-----|-------------|
| `sap.read` | Lecture d’un endpoint SAP |
| `salesforce.query` | Exécute une requête SOQL |
| `sap.inspect` | Liste les endpoints SAP (via metadata) |
| `salesforce.inspect` | Liste des objets Salesforce |
| `client.create` | Création d’un client |
| `ticket.list` | Lecture des tickets |
| `interaction.log` | Journalisation des appels LLM |

---

## 🛠 Scripts utiles

- `run_worker.bat` → pour RabbitMQ (facultatif)
- `start_server.ps1` → lancement auto FastAPI
- `install_mcp.ps1` (à créer) → MCP install automatisé

---

## 📈 Suivi / Backlog

- 🔲 Prompts Claude (via `prompts.yaml`)
- 🔲 `salesforce.populate` pour créer 10 comptes test
- 🔲 Ajout `updated_at` sur tous les modèles
- 🔲 Stats API `/stats` (tickets par client, etc.)
- 🔲 Front React (si version publique souhaitée)

---

© 2025 IT Spirit – Projet NOVA Middleware
