# 🚀 NOVA Middleware - MCP Quickstart (Claude + Salesforce + SAP)

## 🎯 Objectif
Serveur Python compatible Claude Desktop (MCP) exposant :
- `salesforce_query(query: str)`
- `sap_read(endpoint: str, method: str, payload: dict = None)`

## 📁 Arborescence
```
C:\Users\PPZ\NOVA\
├── server_mcp.py        # Serveur MCP Claude
├── main.py              # API REST
├── tools.py             # Fonctions SAP / Salesforce
├── .env                 # Accès API
├── start_server_debug.ps1  # Script double terminal (Claude Inspector)
```

## ⚙️ Setup rapide
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## 🔐 .env requis
```ini
API_KEY=...
SALESFORCE_USERNAME=...
SALESFORCE_PASSWORD=...
SAP_USER=...
SAP_PASSWORD=...
SAP_CLIENT=...
SAP_REST_BASE_URL=...
```

## 🧪 Test MCP local
```powershell
./start_server_debug.ps1
```
➡️ ouvre :  
- 1 terminal pour `server_mcp.py`  
- 1 interface web Claude-like [http://127.0.0.1:6274](http://127.0.0.1:6274)

## 🛠 Exemples de test
### Salesforce
```
SELECT Id, Name FROM Account LIMIT 1
```
### SAP
```
endpoint: /Items
method: GET
```

## ✅ Checklist POC
| Étape | OK |
|-------|----|
| server_mcp.py en STDIO | ✅ |
| Outils détectés (`@tool`) | ✅ |
| Test Claude local via mcp dev | ✅ |
| Connexions SAP/Salesforce | ✅ |

---

Philippe Perez - IT Spirit Dream Team