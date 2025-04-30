# NOVA Middleware - Claude + Salesforce + SAP B1

## 🚀 Présentation

**NOVA Middleware** est une passerelle FastAPI + MCP permettant d'interfacer Claude (LLM), Salesforce et SAP Business One.

Elle expose deux interfaces :
- une **API REST modulaire** (Postman compatible)
- un **serveur MCP (Claude Desktop)** exposant les outils `salesforce.query` et `sap.read`

---

## 🧱 Structure du projet

```
NOVA/
├── main.py                     # Entrée FastAPI avec include_router(...)
├── server_mcp.py               # Serveur Claude MCP (stdio)
├── tools.py                    # Outils MCP (Salesforce, SAP)
├── routes/
│   ├── routes_claude.py        # /claude (LLM API)
│   ├── routes_salesforce.py    # /salesforce_*
│   └── routes_sap.py           # /sap_*
├── services/
│   ├── salesforce.py           # Connexion Salesforce
│   └── sap.py                  # Connexion SAP + gestion session
├── .env                        # Variables sensibles
├── server.yaml                 # Config Claude MCP
├── requirements.txt
├── start_server_debug.ps1      # Lance REST + MCP Inspector + Claude
└── start_server.ps1            # Lance juste MCP (Claude Desktop)
```

---

## ✅ Lancer le projet

### 1. Installer les dépendances

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configurer `.env` :

Contient toutes les clés (Claude, Salesforce, SAP).

### 3. Lancer en développement :

```powershell
./start_server_debug.ps1
```

- Ouvre deux consoles : REST API + MCP Inspector
- Lance aussi `server_mcp.py` pour Claude Desktop

---

## 📮 API REST (Postman)

Toutes les routes sont accessibles via :

- `POST http://127.0.0.1:8000/claude`
- `POST http://127.0.0.1:8000/salesforce_query`
- `POST http://127.0.0.1:8000/sap_query`

> Authentification : `x-api-key: ITS2025`

---

## 🤖 Claude (MCP)

Outils exposés automatiquement :
- `salesforce.query`
- `sap.read`

Compatible Claude Desktop (via `mcp install server_mcp.py`) ou `mcp dev`.

---

## 🔐 Sécurité

- Toutes les routes REST et WebSocket sont protégées par `x-api-key`
- Aucun secret n’est codé en dur
- SAP communique en HTTPS

---

## 👨‍💻 Développeurs

- Philippe Perez (IT Spirit)
- Refacto : avril 2025

---

## 🧪 Tests recommandés Postman

### Claude
```http
POST /claude
{
  "prompt": "Quel est le chiffre d'affaires moyen d'une PME ?"
}
```

### Salesforce
```http
POST /salesforce_query
{
  "query": "SELECT Id, Name FROM Account LIMIT 1"
}
```

### SAP
```http
POST /sap_query
{
  "endpoint": "/Items",
  "method": "GET"
}
```

---

## 🛠️ Prochaines idées

- Ajout de `routes_monday.py`, `routes_openai.py`, etc.
- Intégration `qdrant` pour enrichissement sémantique