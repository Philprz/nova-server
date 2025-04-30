# NOVA Middleware - Salesforce + SAP + Claude LLM

## 🚀 Présentation

**NOVA Middleware** est un serveur FastAPI et MCP permettant d'orchestrer les échanges entre Salesforce, SAP Business One et Claude (Anthropic LLM).  
Il expose à la fois :
- une **API REST** classique (Postman-friendly),
- une **interface WebSocket MCP** pour outils connectés (ex : Claude Desktop).

Ce middleware facilite la génération de devis, la consultation de stocks et la récupération d'informations commerciales de manière automatisée, rapide et sécurisée.

---

## 🛠️ Technologies utilisées

- **Python 3.10+**
- **FastAPI** (serveur HTTP)
- **MCP Protocol** (serveur pour LLMs type Claude)
- **Salesforce** (via `simple-salesforce`)
- **SAP Business One** REST APIs
- **Anthropic Claude 3.7 Sonnet** (LLM externe)
- **WebSocket** pour le mode MCP
- **OVH Windows Server 2019** (infrastructure)
- **Docker** (optionnel - pas activé dans la version actuelle)

---

## 👤 Structure du projet

```
C:\Users\PPZ\NOVA\
├── server_mcp.py        # Serveur officiel MCP (mode stdio)
├── main.py              # API REST classique pour debug / Postman
├── test_mcp_ws.py       # Script de test WebSocket (connexion + requête simple)
├── tools.py             # Outils MCP : requêtes Salesforce & SAP
├── server.yaml          # Configuration du serveur MCP
├── .env                 # Variables sensibles (API Keys, accès Salesforce et SAP)
├── requirements.txt     # Dépendances Python
├── start_server.ps1     # Script de démarrage serveur (optionnel)
├── start_server_debug.ps1 # Script MCP + test local automatique
```

---

## ⚙️ Installation et lancement rapide

### 1. Pré-requis

- Windows Server 2019
- Python 3.10+ installé

Créer un environnement virtuel :
```bash
python -m venv venv
venv\Scripts\activate
```

Installer les dépendances :
```bash
pip install -r requirements.txt
```

---

### 2. Configuration

Compléter le fichier `.env` avec :

| Variable | Description |
|:--------|:------------|
| `API_KEY` | Clé API interne utilisée pour sécuriser REST et WebSocket |
| `ANTHROPIC_API_KEY` | Clé d'API Claude (Anthropic) |
| `SALESFORCE_USERNAME`, `SALESFORCE_PASSWORD`, `SALESFORCE_SECURITY_TOKEN` | Accès Salesforce |
| `SAP_USER`, `SAP_PASSWORD`, `SAP_CLIENT`, `SAP_REST_BASE_URL` | Accès SAP B1 REST API |

---

### 3. Lancer le serveur MCP (Claude)

```bash
python server_mcp.py
```
- Mode **stdio** obligatoire pour être détecté par Claude Desktop.
- Le serveur expose automatiquement les outils `salesforce.query` et `sap.read`.

---

### 4. Démarrage en mode debug (recommandé)

```powershell
./start_server_debug.ps1
```
- Ouvre 2 terminaux :
  - Serveur MCP
  - Interface web de test via `mcp dev`

Tu peux ensuite aller sur [http://127.0.0.1:6274](http://127.0.0.1:6274) pour utiliser l’interface Claude-like MCP Inspector.

---

## ✅ Résumé de mise en place MCP

| Étape | Statut |
|:------|:-------|
| `server_mcp.py` fonctionnel et détecté par Claude Desktop | ✅ |
| Outils `@mcp.tool()` bien exposés (Salesforce + SAP) | ✅ |
| Lancement via `mcp dev` ou `Claude Desktop` OK | ✅ |
| Variables `.env` chargées automatiquement | ✅ |
| Tests réalisés via MCP Inspector Web | ✅ |

---

## 🔧 Exemples de test dans MCP Inspector

### `salesforce_query`
```text
SELECT Id, Name FROM Account LIMIT 1
```

### `sap_read`
- `endpoint`: `/Items`
- `method`: `GET`
- `payload`: (laisser vide)

---

## 🛡️ Sécurité

- Toutes les routes REST/WebSocket sont protégées par une vérification `x-api-key`.
- Les accès Salesforce et SAP sont stockés en variables d'environnement sécurisées (`.env`).
- Communication SAP via HTTPS (self-signed possible pour DEV).

---

## 📋 Fonctionnalités principales

| Fonctionnalité | Description |
|:-------------|:------------|
| `salesforce.query` | Exécuter une requête SOQL sur Salesforce |
| `sap.read` | Lire des données SAP Business One REST (produits, stocks, devis) |
| `ask_claude` | Envoyer une requête LLM à Claude 3.7 (prompt + réponse enrichie) |
| Cache SAP | Gestion automatique de session SAP et rafraîchissement des cookies |
| Heartbeat MCP | Ping automatique toutes les 30s pour maintenir la connexion active |

---

## 🧐 Points de vigilance

- **Claude Desktop** attend une structure MCP en STDIO avec `mcp.run()` (ne pas utiliser `asyncio.run()`).
- L’interface `mcp dev` nécessite `npx` et Node.js pour l’Inspector Web.
- Les paramètres MCP doivent être simples (`str`, `int`, etc.) ou des objets Pydantic typés.

---

## 👨‍💻 Développeurs

- **Philippe Perez** (IT Spirit Dream Team) – Lead Developer
- **Bruno Charnal** – Support Technique ponctuel

---

# 📢 Important
Ce middleware est actuellement en phase **POC** (Proof of Concept) et n'est **pas encore optimisé pour un usage intensif en production** sans audit complémentaire de performance et sécurité.