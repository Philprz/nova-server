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
├── autres fichiers      # (documents projet, docx)
```

---

## ⚙️ Installation et lancement rapide

### 1. Pré-requis

- Windows Server 2019
- Python 3.10+ installé
- Créer un environnement virtuel :

```bash
python -m venv venv
venv\Scripts\activate
```

- Installer les dépendances :

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

### 4. Lancer le serveur REST (Postman)

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```
- Permet de tester manuellement via HTTP :
  - `/claude` : envoyer un prompt vers Claude.
  - `/salesforce_query` : envoyer une requête SOQL.
  - `/sap_query` : interroger SAP B1.

---

### 5. Tester en local via WebSocket

```bash
python test_mcp_ws.py
```
- Ce script connecte un client WebSocket, s'authentifie, et envoie une requête Salesforce de test.

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

> (résumé basé sur le document interne "Points de Vigilance")

- **Accès API** : Vérifier dès le départ que SAP expose bien les endpoints nécessaires.
- **Qualité données** : Les données SAP doivent être fiables pour éviter hallucinations LLM.
- **Performance** : Objectif : réponses commerciales en < 5 secondes.
- **Scalabilité** : Anticiper coûts API Claude à fort volume.
- **Sécurité & RGPD** : Logging sécurisé, chiffrement des données sensibles, audit de conformité.

---

## 🗓️ Planning initial du projet

| Phase | Détail |
|:------|:-------|
| S1-S2 | Installation serveur + Connexion API Salesforce / SAP |
| S3-S5 | Développement Middleware (REST, MCP, Cache) |
| S6-S8 | Développement cas d'usage Devis Salesforce |
| S9-S10 | Tests finaux, optimisations, documentation et démo |

---

## 🔮 Roadmap potentielle

- Support OAuth2 Salesforce (au lieu de user+password)
- Mode Docker/Linux
- Interface web frontale (React / Lightning Web Component)
- Monitoring API usage & coûts en production

---

## 👨‍💻 Développeurs

- **Philippe Perez** (IT Spirit Dream Team) – Lead Developer
- **Bruno Charnal** – Support Technique ponctuel

---

# 📢 Important
Ce middleware est actuellement en phase **POC** (Proof of Concept) et n'est **pas encore optimisé pour un usage intensif en production** sans audit complémentaire de performance et sécurité.

