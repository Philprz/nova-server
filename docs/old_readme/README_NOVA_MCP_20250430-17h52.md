# NOVA Middleware - Claude + Salesforce + SAP B1

**NOVA Middleware** est une passerelle FastAPI + MCP permettant d'interfacer :

- **Claude** (LLM via MCP)
- **Salesforce** (SOQL)
- **SAP Business One** (REST API)

Elle expose :
- une **API REST** (Postman/HTTPie compatibles)
- un **serveur MCP** pour **Claude Desktop** (via stdio)

---

## 🧱 Structure du projet

```
NOVA/
├── main.py                     # Entrée FastAPI
├── server_mcp.py               # Serveur MCP (Claude Desktop)
├── mcp_app.py                  # Initialisation MCP
├── tools.py                    # Outils métier MCP (Salesforce, SAP)
├── services/                   # Logique métier pour REST
│   ├── salesforce.py           # Connexion Salesforce
│   ├── sap.py                  # Connexion SAP
│   ├── exploration_salesforce.py  # Exploration Salesforce
│   └── exploration_sap.py         # Exploration SAP
├── routes/                     # Routes FastAPI REST
│   ├── routes_claude.py        # /claude (LLM)
│   ├── routes_salesforce.py    # /salesforce_query, /salesforce_create_account
│   └── routes_sap.py           # /sap_query, /sap_login_test
├── alembic/                    # Migrations de schéma (Alembic)
├── prompts.yaml                # Templates de prompts LLM
├── server.yaml                 # Configuation Claude MCP
├── .env                        # Variables d'environnement
├── requirements.txt            # Dépendances Python
├── run_worker.bat              # Lancement du worker RabbitMQ
└── start_server.ps1            # Script de démarrage (PowerShell)
```

---

## ✅ Prérequis

- **Windows 2019 Server** (Docker non requis)
- **Python 3.10**
- **PostgreSQL >= 15** (UTF8)
- **RabbitMQ** + Erlang installés localement
- Variables d’environnement dans `.env`

---

## ⚙️ Installation & configuration

1. **Cloner le projet**  
   ```bash
git clone <repo-url> NOVA
cd NOVA
```
2. **Créer et activer le venv**  
   ```bash
python -m venv venv
.\venv\Scripts\Activate.ps1
```
3. **Installer les dépendances**  
   ```bash
pip install -r requirements.txt
```
4. **Installer et configurer PostgreSQL**  
   - Installe PostgreSQL (encodage UTF8).  
   - Dans pgAdmin ou psql, crée la base et l’utilisateur :
     ```sql
     CREATE DATABASE nova_mcp
       WITH OWNER = nova_user
            ENCODING = 'UTF8'
            LC_COLLATE = 'C'
            LC_CTYPE   = 'C'
            TEMPLATE   = template0;
     CREATE USER nova_user WITH ENCRYPTED PASSWORD 'votre_mdpp';
     GRANT ALL PRIVILEGES ON DATABASE nova_mcp TO nova_user;
     ```
5. **Configurer Alembic**  
   - Initialise si nécessaire : `alembic init alembic`  
   - Vérifie `DATABASE_URL` dans `.env` et `alembic/env.py`.  
   - Génère et applique la première migration :
     ```bash
     alembic revision --autogenerate -m "Initial schema"
     alembic upgrade head
     ```
6. **Installer et démarrer RabbitMQ**  
   - Installe Erlang puis RabbitMQ (activant `rabbitmq_management`).  
   - Vérifie l’UI : http://localhost:15672 (guest/guest)  
   - Crée `run_worker.bat` pour lancer `python worker.py` et configure-le en tâche planifiée (Task Scheduler) au démarrage.  
7. **Créer le fichier `prompts.yaml`**  
   ```yaml
   salesforce_query:
     description: "Génère un SOQL pour récupérer compte et opportunités"
     template: |
       Vous êtes un expert Salesforce. Écrivez une requête SOQL pour récupérer tous les champs
       du compte dont l’ID est {{ account_id }} et ses 10 dernières opportunités.

   sap_item_lookup:
     description: "Récupère prix et stock pour une liste de codes articles"
     template: |
       Vous êtes un expert SAP B1. Pour chaque code article dans {{ item_codes }},
       renvoyez un JSON listant "ItemCode", "Price", "Stock".
   ```

---

## ▶️ Démarrage des services

- **REST API (FastAPI)** :  
  ```bash
  uvicorn main:app --reload
  ```
- **Serveur MCP** :  
  ```bash
  mcp dev server_mcp.py --with-editable .
  ```
- **Claude Desktop** :  
  ```bash
  mcp install server_mcp.py --name nova_middleware -f .env
  ```
- **Worker RabbitMQ** :  
  - Tâche planifiée Windows ou manuellement :  
    ```bash
    run_worker.bat
    ```

---

## 📮 API REST

Tous les endpoints requièrent `x-api-key: <API_KEY>` :

- `POST /claude`  
- `POST /salesforce_query`  
- `POST /salesforce_create_account`  
- `POST /sap_query`  
- `GET /sap_login_test`

---

## 🧪 Tests & automatisation

- **Migrations** : `alembic upgrade head`  
- **Protocol MCP** : `test_mcp_ws.py`  
- **Collection Postman / .http** : dans `tests/`  

---

## 🔐 Sécurité

- Clé API REST (`API_KEY`) et clés LLM (`ANTHROPIC_API_KEY`) gérées via `.env`  
- Connexus SAP/SSL sans vérification locale désactivée en dev  

---

## 🚀 Suite du POC

- **Phase Alembic & migrations** (suite en nouvelle session)  
- **Workflow devis** et composant Lightning  
- **Gestion des cas particuliers**, performance et démo finale

---

© 2025 IT Spirit

