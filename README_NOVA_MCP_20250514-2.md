# NOVA Middleware - Claude + Salesforce + SAP B1

**NOVA Middleware** est une passerelle permettant d'intégrer:
- 🧠 Claude (LLM via MCP)
- ☁️ Salesforce (SOQL API)
- 🏭 SAP Business One (REST API)
- 🗃️ PostgreSQL (stockage interne)

---

## 🚀 Mise à jour du 14 mai 2025

### Nouveautés

- ✅ Implémentation complète des serveurs MCP (Model Context Protocol)
- ✅ Fonctionnalités étendues pour Salesforce et SAP
- ✅ Correction des problèmes de compatibilité avec Claude Desktop
- ✅ Standardisation des noms d'outils (format compatible)
- ✅ Documentation des outils disponibles
- ✅ Scripts de démarrage améliorés
- ✅ **Nouveau workflow de devis intelligent**
- ✅ **Intégration LLM pour extraction de données**
- ✅ **Interface utilisateur Salesforce (LWC)**

### Problèmes résolus

- ✓ Correction du format des noms d'outils MCP pour Claude Desktop
- ✓ Gestion des erreurs et journalisation améliorées
- ✓ Structure de cache optimisée
- ✓ Résolution des problèmes de session SAP
- ✓ **Mécanisme de fallback pour l'extraction**

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
├── salesforce_mcp.py            # Serveur MCP Salesforce complet
├── sap_mcp.py                   # Serveur MCP SAP complet
├── start_mcp_servers.ps1        # Script de démarrage amélioré
├── start_nova_devis.ps1         # Script démarrage workflow devis
├── db/
│   ├── models.py                # Modèles SQLAlchemy
│   └── session.py               # Connexion DB / get_db()
├── routes/
│   ├── ...                      # Endpoints CRUD FastAPI
│   └── routes_devis.py          # Endpoints workflow devis
├── services/
│   ├── exploration_sap.py       # Inspection SAP
│   ├── exploration_salesforce.py # Inspection Salesforce
│   ├── sap.py                   # Connecteur SAP
│   ├── salesforce.py            # Connecteur Salesforce
│   ├── mcp_connector.py         # Connecteur outils MCP
│   └── llm_extractor.py         # Extraction LLM
├── workflow/
│   └── devis_workflow.py        # Orchestrateur workflow devis
├── force-app/                   # Composants Salesforce (LWC)
│   └── main/default/lwc/novaDevisGenerator/
├── logs/                        # Répertoire pour les logs MCP
├── cache/                       # Cache des métadonnées
├── test_mcp_tools.py            # Tests des outils MCP
├── .env                         # Secrets (Salesforce, DB, API)
├── Documentation_MCP_NOVA.md    # Documentation des outils MCP
├── Documentation_Workflow_Devis.md # Documentation workflow
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
# Démarrer tous les services MCP
.\start_mcp_servers.ps1

# Démarrer le workflow de devis
.\start_nova_devis.ps1 -Verbose
```

Ces scripts :
- Activent l'environnement virtuel
- Vérifient/installent les dépendances requises
- Créent les dossiers logs/ et cache/ si nécessaire
- Démarrent les serveurs MCP et FastAPI
- Affichent les instructions de configuration

---

## 🧠 Configuration Claude Desktop

Pour intégrer les outils MCP avec Claude Desktop :

1. Créez ou mettez à jour le fichier dans `%APPDATA%\Claude\claude_desktop_config.json` :

```json
{
  "mcpServers": {
    "salesforce_mcp": {
      "command": "python",
      "args": ["C:\\Users\\PPZ\\NOVA\\salesforce_mcp.py"],
      "cwd": "C:\\Users\\PPZ\\NOVA",
      "envFile": ".env",
      "stdio": true
    },
    "sap_mcp": {
      "command": "python",
      "args": ["C:\\Users\\PPZ\\NOVA\\sap_mcp.py"],
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

## 📋 Workflow de Devis

Le nouveau workflow de devis permet aux commerciaux de générer automatiquement des devis à partir de demandes en langage naturel.

### Fonctionnalités
- Analyse des demandes en langage naturel via Claude
- Validation du client dans Salesforce
- Récupération des informations produits depuis SAP
- Vérification de la disponibilité et alternatives
- Création automatique de devis dans Salesforce

### Utilisation
1. Saisissez une demande en langage naturel :
```
"Faire un devis pour 10 ordinateurs portables A23567 pour le client ACME"
```

2. Le système orchestrera automatiquement :
   - L'extraction des informations (client, produits, quantités)
   - La validation du client dans Salesforce
   - La vérification des stocks dans SAP
   - La proposition d'alternatives si nécessaire
   - La création du devis dans Salesforce

### API REST
- `POST /generate_quote` : Génère un devis à partir d'une demande
- `POST /update_quote` : Met à jour un devis avec alternatives

### Interface Salesforce
Le composant Lightning Web Component `novaDevisGenerator` est disponible pour intégration dans les pages Account et Opportunity de Salesforce.

Pour plus de détails, consultez `Documentation_Workflow_Devis.md`.

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
- `POST /generate_quote` (Nouveau)
- `POST /update_quote` (Nouveau)

Documentation API interactive :
- Swagger UI : http://localhost:8000/docs
- ReDoc : http://localhost:8000/redoc

---

## 🧰 Outils Claude (MCP)

| Outil | Description |
|-------|-------------|
| `ping` | Test de disponibilité du serveur MCP |
| `salesforce_query` | Exécute une requête SOQL sur Salesforce |
| `salesforce_inspect` | Liste les objets et champs Salesforce |
| `salesforce_refresh_metadata` | Force la mise à jour des métadonnées Salesforce |
| `sap_read` | Lit des données SAP via API REST |
| `sap_inspect` | Liste les endpoints SAP disponibles |
| `sap_refresh_metadata` | Force la mise à jour des métadonnées SAP |
| `sap_search` | Recherche des entités dans SAP |
| `sap_get_product_details` | Récupère les détails d'un produit |
| `sap_check_product_availability` | Vérifie la disponibilité d'un produit |
| `sap_find_alternatives` | Trouve des produits alternatifs |
| `sap_create_draft_order` | Crée un brouillon de commande |

Pour une documentation détaillée des outils, consultez le fichier `Documentation_MCP_NOVA.md`.

Exemples d'utilisation dans Claude Desktop :
```
# Test simple
ping

# Requête Salesforce
salesforce_query("SELECT Id, Name FROM Account LIMIT 5")

# Inspection d'un objet Salesforce
salesforce_inspect("Account")

# Lecture de données SAP
sap_read("/Items", "GET")
```

---

## 🪲 Résolution des problèmes courants

### Erreur "tools.FrontendRemoteMcpToolDefinition.name: String should match pattern..."

Cette erreur est liée au format de nommage des outils MCP dans Claude Desktop. Les noms des outils ne doivent contenir que des lettres, chiffres, tirets et underscores. Les points (`.`) ne sont pas autorisés.

Solution : Les noms d'outils ont été standardisés pour utiliser des underscores à la place des points (ex: `salesforce_query` au lieu de `salesforce.query`).

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
4. Si nécessaire, utilisez la version minimale avec l'option `-Minimal` :
   ```powershell
   .\start_mcp_servers.ps1 -Minimal
   ```

### Session SAP expirée

```python
# Rafraîchir manuellement la session SAP
sap_refresh_session()
```

---

## 📊 Journalisation et débogage

Les serveurs MCP écrivent des logs détaillés dans les fichiers :
- `logs/salesforce_mcp.log`
- `logs/sap_mcp.log`
- `logs/workflow_devis.log` (Nouveau)

Pour tester les connexions directement :
```powershell
python test_mcp_tools.py
```

---

## 📈 Prochaines étapes

- 🔲 Intégration de l'historique client pour des suggestions personnalisées
- 🔲 Interface conversationnelle pour affiner les devis
- 🔲 Intégration avec le workflow d'approbation Salesforce
- 🔲 Intégration JIRA, Zendesk et Confluence
- 🔲 Mise en place de Qdrant pour la documentation
- 🔲 Tests utilisateurs et optimisations

---

## 📚 Documentation MCP

Pour approfondir vos connaissances sur MCP (Model Context Protocol), consultez :

- [Documentation officielle MCP](https://modelcontextprotocol.io/docs/)
- [GitHub du projet MCP](https://github.com/anthropics/anthropic-tools)
- [Exemples de serveurs MCP](https://github.com/anthropics/anthropic-tools/tree/main/examples)

---

© 2025 IT Spirit – Projet NOVA Middleware