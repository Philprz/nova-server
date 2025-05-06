# NOVA Middleware - Claude + Salesforce + SAP B1

## 🚀 Présentation

**NOVA Middleware** est une passerelle FastAPI + MCP permettant d'interfacer :
- **Claude** (LLM via MCP)
- **Salesforce** (SOQL)
- **SAP Business One** (REST API)

Elle expose :
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
├── server.yaml                 # Config Claude MCP
├── .env                        # Variables d'environnement
├── requirements.txt            # Dépendances Python
└── start_server.ps1            # Script de démarrage (PowerShell)
```

---

## ✅ Installation et démarrage

1. **Cloner le projet**  
   ```bash
   git clone <repo-url> NOVA
   ```
2. **Créer et activer le venv**  
   ```bash
   cd NOVA
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```
3. **Installer les dépendances**  
   ```bash
   pip install -r requirements.txt
   ```
4. **Configurer le fichier `.env`**  
   Remplir les clés :  
   - `ANTHROPIC_API_KEY`, `API_KEY`  
   - Salesforce : `SALESFORCE_*`  
   - SAP : `SAP_*`
5. **Lancer les serveurs**  
   - **REST API (FastAPI)** :  
     ```bash
     uvicorn main:app --reload
     ```  
   - **MCP Inspector** *(dev)* :  
     ```bash
     mcp dev server_mcp.py --with-editable .
     ```  
   - **Claude Desktop** :  
     ```bash
     mcp install server_mcp.py --name nova_middleware -f .env
     ```

---

## 📮 API REST

Routes protégées par `x-api-key: <API_KEY>` :

- `POST /claude`  
- `POST /salesforce_query`  
- `POST /salesforce_create_account`  
- `POST /sap_query`  
- `GET  /sap_login_test`  

---

## 🤖 Outils MCP (Claude Desktop)

Expose via `server.yaml` et `mcp_app.py` :

### Salesforce  
- `salesforce.query(query: str)`  
- `salesforce.inspect([object_name])`  
- `salesforce.refresh_metadata()`  

### SAP  
- `sap.read(endpoint: str, method, payload)`  
- `sap.inspect()`  
- `sap.refresh_metadata()`  

---

## 🔍 Exploration automatique

Les outils `inspect`/`refresh_metadata` forcent ou lisent le cache JSON local pour permettre à Claude de :

- découvrir dynamiquement la structure Salesforce  
- lister ou rafraîchir les endpoints SAP  

---

## 🧪 Tests

- Utiliser `test_mcp_ws.py` pour valider le protocole MCP  
- Collection Postman / `.http` disponible dans `tests/`

---

## 🔐 Sécurité

- Tous les endpoints REST nécessitent `x-api-key`  
- Les secrets sont gérés via `.env` (dotenv)  
- Communication SAP en HTTPS (vérification désactivée localement)  

---

## 👥 Contributeurs

- Philippe Perez (IT Spirit)  
- Refactorisation : avril 2025  
