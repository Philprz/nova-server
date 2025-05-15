NOVA Middleware - Claude + Salesforce + SAP B1
NOVA Middleware est une passerelle permettant d'intégrer:

🧠 Claude (LLM via MCP)
☁️ Salesforce (SOQL API)
🏭 SAP Business One (REST API)
🗃️ PostgreSQL (stockage interne)


🚀 Mise à jour du 14 mai 2025
Nouveautés

✅ Implémentation complète des serveurs MCP (Model Context Protocol)
✅ Fonctionnalités étendues pour Salesforce et SAP
✅ Correction des problèmes de compatibilité avec Claude Desktop
✅ Standardisation des noms d'outils (format compatible)
✅ Documentation des outils disponibles
✅ Scripts de démarrage améliorés
✅ Nouveau workflow de devis intelligent
✅ Intégration LLM pour extraction de données
✅ Interface utilisateur Salesforce (LWC)

Problèmes résolus

✓ Correction du format des noms d'outils MCP pour Claude Desktop
✓ Gestion des erreurs et journalisation améliorées
✓ Structure de cache optimisée
✓ Résolution des problèmes de session SAP
✓ Mécanisme de fallback pour l'extraction


🔧 Prérequis

Windows Server 2019+ (x64)
Python 3.10+
PostgreSQL >= 15 (UTF8)
Claude Desktop installé (MCP compatible)
Variables d'environnement dans .env


📦 Structure du projet
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
├── static/                      # Fichiers statiques pour la démo web
├── test_mcp_tools.py            # Tests des outils MCP
├── .env                         # Secrets (Salesforce, DB, API)
├── Documentation_MCP_NOVA.md    # Documentation des outils MCP
├── Documentation_Workflow_Devis.md # Documentation workflow
└── README.md                    # Documentation

⚙️ Installation
bashgit clone <repo> NOVA
cd NOVA
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Mise à jour des dépendances
Si vous migrez depuis une version antérieure ou rencontrez des problèmes :
bash.\venv\Scripts\Activate.ps1
pip install simple-salesforce mcp httpx fastapi uvicorn python-dotenv --upgrade
Fichier .env requis
ANTHROPIC_API_KEY=votre_clé_api_anthropic
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

🚀 Démarrage rapide
powershell# Démarrer tous les services MCP
.\start_mcp_servers.ps1

# Démarrer le workflow de devis
.\start_nova_devis.ps1 -Verbose
Ces scripts :

Activent l'environnement virtuel
Vérifient/installent les dépendances requises
Créent les dossiers logs/ et cache/ si nécessaire
Démarrent les serveurs MCP et FastAPI
Affichent les instructions de configuration


🧠 Configuration Claude Desktop
Pour intégrer les outils MCP avec Claude Desktop :

Créez ou mettez à jour le fichier dans %APPDATA%\Claude\claude_desktop_config.json :

json{
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

Relancez Claude Desktop
Activez les outils via l'interface de Claude Desktop (bouton "+")


📋 Workflow de Devis
Le nouveau workflow de devis permet aux commerciaux de générer automatiquement des devis à partir de demandes en langage naturel.
Fonctionnalités

Analyse des demandes en langage naturel via Claude
Validation du client dans Salesforce
Récupération des informations produits depuis SAP
Vérification de la disponibilité et alternatives
Création automatique de devis dans Salesforce

Utilisation

Saisissez une demande en langage naturel :

"Faire un devis pour 10 ordinateurs portables A23567 pour le client ACME"

Le système orchestrera automatiquement :

L'extraction des informations (client, produits, quantités)
La validation du client dans Salesforce
La vérification des stocks dans SAP
La proposition d'alternatives si nécessaire
La création du devis dans Salesforce



API REST

POST /generate_quote : Génère un devis à partir d'une demande
POST /update_quote : Met à jour un devis avec alternatives

Interface démo
Une interface HTML statique est disponible à l'adresse http://localhost:8000/static/demo_devis.html pour tester le workflow sans avoir besoin de l'intégration Salesforce.
Interface Salesforce
Le composant Lightning Web Component novaDevisGenerator est disponible pour intégration dans les pages Account et Opportunity de Salesforce.
Pour plus de détails, consultez Documentation_Workflow_Devis.md.

🔌 API REST (FastAPI)
Endpoints disponibles :

POST /clients
GET /clients
POST /utilisateurs
POST /tickets
POST /factures
POST /interactions_llm
POST /salesforce_query
POST /sap_query
GET /sap_login_test
POST /generate_quote
POST /update_quote

Documentation API interactive :

Swagger UI : http://localhost:8000/docs
ReDoc : http://localhost:8000/redoc


🧰 Outils Claude (MCP)
OutilDescriptionpingTest de disponibilité du serveur MCPsalesforce_queryExécute une requête SOQL sur Salesforcesalesforce_inspectListe les objets et champs Salesforcesalesforce_refresh_metadataForce la mise à jour des métadonnées Salesforcesap_readLit des données SAP via API RESTsap_inspectListe les endpoints SAP disponiblessap_refresh_metadataForce la mise à jour des métadonnées SAPsap_searchRecherche des entités dans SAPsap_get_product_detailsRécupère les détails d'un produitsap_check_product_availabilityVérifie la disponibilité d'un produitsap_find_alternativesTrouve des produits alternatifssap_create_draft_orderCrée un brouillon de commande
Pour une documentation détaillée des outils, consultez le fichier Documentation_MCP_NOVA.md.
Exemples d'utilisation dans Claude Desktop :
# Test simple
ping

# Requête Salesforce
salesforce_query("SELECT Id, Name FROM Account LIMIT 5")

# Inspection d'un objet Salesforce
salesforce_inspect("Account")

# Lecture de données SAP
sap_read("/Items", "GET")

🪲 Tests et débogage
Pour vérifier les connexions aux services externes:
powershell# Test complet des outils MCP
python test_mcp_tools.py

# Test spécifique de Salesforce
python test_salesforce_query.py

# Test spécifique du workflow de devis
python tests/test_devis_workflow.py

# Débogage ciblé du workflow
python debug_workflow.py
Les serveurs MCP écrivent des logs détaillés dans:

logs/salesforce_mcp.log
logs/sap_mcp.log
logs/workflow_devis.log

Pour forcer le mode réel (sans démo), modifiez la condition dans routes/routes_devis.py en désactivant temporairement le mode démo.

🛠️ Configuration pour mode démo/production
Le système peut fonctionner en deux modes:
Mode démo
Activé automatiquement lorsque les requêtes contiennent les mots-clés "demo", "edge" ou "a00001".
Retourne des réponses prédéfinies sans appeler les services externes réels.
Mode production
Utilise les vrais connecteurs pour Salesforce et SAP.
Requiert que toutes les connexions fonctionnent correctement.
Pour forcer l'utilisation du mode production même pour les tests, modifiez la fonction generate_quote dans routes_devis.py:
python# Remplacer cette ligne
demo_mode = "demo" in request.prompt.lower() or "edge" in request.prompt.lower() or "a00001" in request.prompt.lower()

# Par celle-ci pour désactiver le mode démo
demo_mode = False

📈 Prochaines étapes

🔲 Intégration de l'historique client pour des suggestions personnalisées
🔲 Interface conversationnelle pour affiner les devis
🔲 Intégration avec le workflow d'approbation Salesforce
🔲 Intégration JIRA, Zendesk et Confluence
🔲 Mise en place de Qdrant pour la documentation
🔲 Tests utilisateurs et optimisations


© 2025 IT Spirit – Projet NOVA Middleware