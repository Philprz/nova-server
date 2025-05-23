# NOVA Middleware - Documentation

## Vue d'ensemble

NOVA Middleware est une plateforme d'intégration intelligente permettant de connecter:

- 🧠 **Claude** (LLM via MCP)
- ☁️ **Salesforce** (CRM)
- 🏭 **SAP Business One** (ERP)
- 🗃️ **PostgreSQL** (stockage interne)

Cette solution facilite l'interaction entre ces systèmes via des outils MCP (Model Context Protocol) et des workflows orchestrés, permettant notamment la génération automatique de devis à partir de requêtes en langage naturel.

## 🚀 Nouveautés - Mai 2025

### Améliorations (v1.2.0 - 15/05/2025)

- ✅ Correction de l'extracteur LLM (bug sur le traitement des réponses Claude)
- ✅ Amélioration des connecteurs MCP avec gestion avancée des erreurs
- ✅ Robustesse accrue pour la recherche et validation client
- ✅ Journalisation détaillée des interactions systèmes
- ✅ Mécanismes de fallback améliorés (extraction manuelle si LLM échoue)
- ✅ Correction des duplications de code dans le workflow de devis

### Corrections de bugs

- ✓ Résolution du problème "Client non trouvé" avec Edge Communications
- ✓ Traitement correctif de la structure JSON dans les réponses API Claude
- ✓ Nettoyage des fichiers temporaires MCP
- ✓ Gestion des caractères spéciaux dans les requêtes Salesforce
- ✓ Fiabilité lors de la connexion aux systèmes externes

## 🏗️ Architecture

```
NOVA/
├── main.py                     # Point d'entrée FastAPI
├── salesforce_mcp.py           # Serveur MCP Salesforce
├── sap_mcp.py                  # Serveur MCP SAP
├── db/                         # Couche d'accès aux données
├── routes/                     # Endpoints API
├── services/                   # Services d'intégration
│   ├── llm_extractor.py        # Extraction d'informations via Claude
│   ├── mcp_connector.py        # Connecteur MCP unifié
│   ├── salesforce.py           # Client Salesforce
│   └── sap.py                  # Client SAP
├── workflow/                   # Orchestration métier
│   └── devis_workflow.py       # Workflow génération devis
├── tests/                      # Tests unitaires et intégration
├── logs/                       # Journal d'exécution
└── .env                        # Configuration (non versionné)
```

## 💻 Prérequis

- **Système**: Windows Server 2019+ (x64)
- **Runtime**: Python 3.10+
- **Base de données**: PostgreSQL 15+ (UTF8)
- **Client**: Claude Desktop (MCP compatible)
- **Accès API**:
  - Anthropic API (Claude)
  - Salesforce API
  - SAP Business One Service Layer

## 🛠️ Installation

```bash
# Cloner le dépôt
git clone <repo> NOVA
cd NOVA

# Créer l'environnement virtuel
python -m venv venv
.\venv\Scripts\Activate.ps1

# Installer les dépendances
pip install -r requirements.txt
```

### Configuration

Créez un fichier `.env` à la racine du projet avec les paramètres suivants:

```
ANTHROPIC_API_KEY=votre_clé_api_anthropic
SALESFORCE_USERNAME=utilisateur@exemple.com
SALESFORCE_PASSWORD=votremotdepasse
SALESFORCE_SECURITY_TOKEN=votretokensécurité
SALESFORCE_DOMAIN=login

SAP_REST_BASE_URL=https://votre-serveur-sap:50000/b1s/v1
SAP_USER=utilisateur_sap
SAP_CLIENT=SBODemoFR
SAP_CLIENT_PASSWORD=motdepasse_sap

API_KEY=votre_clé_api_interne

DATABASE_URL=postgresql://nova_user:motdepasse@localhost:5432/nova_mcp
```

## 🚀 Démarrage rapide

```powershell
# Démarrer tous les services
.\start_nova_devis.ps1 -Verbose
```

Ce script:
- Active l'environnement virtuel
- Vérifie/installe les dépendances manquantes
- Crée les dossiers logs/ et cache/ si nécessaires
- Démarre les serveurs MCP et FastAPI
- Affiche les URLs d'accès

## 🧰 Outils disponibles

### Salesforce
- `ping` - Test de disponibilité
- `salesforce_query` - Exécute une requête SOQL
- `salesforce_inspect` - Liste les objets et champs
- `salesforce_refresh_metadata` - Met à jour les métadonnées

### SAP
- `ping` - Test de disponibilité
- `sap_read` - Lit des données via API REST
- `sap_inspect` - Liste les endpoints disponibles
- `sap_refresh_metadata` - Met à jour les endpoints
- `sap_search` - Recherche dans SAP
- `sap_get_product_details` - Détails d'un produit
- `sap_check_product_availability` - Vérifie la disponibilité
- `sap_find_alternatives` - Trouve des alternatives
- `sap_create_draft_order` - Crée un brouillon de commande

## 📦 Workflow de Devis

Le workflow de devis permet aux commerciaux de générer automatiquement des devis à partir de demandes en langage naturel.

### Exemple d'utilisation

Requête en langage naturel:
```
"Faire un devis pour 10 ordinateurs portables A23567 pour le client ACME"
```

Le système orchestre automatiquement:
1. L'extraction des informations (client, produits, quantités)
2. La validation du client dans Salesforce
3. La vérification des stocks dans SAP
4. La proposition d'alternatives si nécessaire
5. La création du devis dans Salesforce

### API REST Devis

- **POST /generate_quote**: Génère un devis à partir d'une demande
- **POST /update_quote**: Met à jour un devis avec alternatives

## 📋 Dépannage

### Logs détaillés

Les fichiers de logs se trouvent dans le répertoire `logs/`:
- `salesforce_mcp.log` - Logs du serveur MCP Salesforce
- `sap_mcp.log` - Logs du serveur MCP SAP
- `workflow_devis.log` - Logs du workflow de devis

### Tests de connexion

Pour vérifier les connexions aux systèmes externes:

```powershell
# Test des outils MCP
python tests/test_mcp_tools.py

# Test spécifique de l'API Salesforce
python tests/test_salesforce_connection.py

# Test du workflow de devis
python tests/test_devis_workflow.py
```

### Problèmes courants

1. **Erreur "Client non trouvé"**
   - Vérifiez l'extraction du nom client (logs/workflow_devis.log)
   - Assurez-vous que le client existe dans Salesforce
   - Vérifiez les stratégies de recherche utilisées

2. **Erreurs de connexion MCP**
   - Vérifiez l'installation des composants MCP
   - Redémarrez Claude Desktop
   - Vérifiez les fichiers de configuration (.env)

3. **Erreurs d'extraction LLM**
   - Vérifiez la validité de la clé API Anthropic
   - Examinez les logs pour voir la réponse brute
   - Testez l'API manuellement avec `tests/test_api_anthropic.py`

## 🧪 Mode démo

Pour activer le mode démo (sans appels aux systèmes réels), modifiez dans `routes/routes_devis.py`:

```python
# Activer le mode démo
demo_mode = True  # Utiliser False pour le mode production
```

## 📈 Prochaines étapes

- 🔲 Intégration de l'historique client pour suggestions personnalisées
- 🔲 Interface conversationnelle pour affiner les devis
- 🔲 Intégration avec le workflow d'approbation Salesforce
- 🔲 Support des produits configurables
- 🔲 Intégration JIRA et Zendesk

---

© 2025 IT Spirit – Projet NOVA Middleware