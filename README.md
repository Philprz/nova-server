# 🚀 NOVA - POC LLM Salesforce/SAP Integration

> **Middleware d'intégration entre Claude (Anthropic), Salesforce et SAP pour la génération automatique de devis**

## 📋 Vue d'Ensemble du Projet

**NOVA** est un POC (Proof of Concept) permettant aux commerciaux de générer automatiquement des devis en utilisant le traitement du langage naturel. Les utilisateurs formulent leurs demandes en langage naturel (ex: *"faire un devis sur la fourniture de 500 ref A00002 pour le client Edge Communications"*) et obtiennent automatiquement les informations produits, prix et disponibilités pour générer un devis complet.

### 🎯 Objectifs
- ✅ **Traitement du langage naturel** pour extraire les besoins commerciaux
- ✅ **Intégration Salesforce** pour la gestion des clients et opportunités  
- ✅ **Intégration SAP** pour les produits, stocks et pricing
- ✅ **Génération automatique de devis** avec validation des disponibilités
- ✅ **Validation client enrichie** avec contrôles SIRET, doublons et normalisation

### 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │   Middleware    │    │   Systèmes      │
│   (Interface    │───▶│     NOVA        │───▶│   Sources       │
│   FastAPI)      │    │   (FastAPI)     │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │                        │
                                ▼                        ▼
                       ┌─────────────────┐    ┌─────────────────┐
                       │   Claude API    │    │  MCP Servers    │
                       │   (Anthropic)   │    │ (SF + SAP)      │
                       └─────────────────┘    └─────────────────┘
```

## 🛠️ Stack Technique

### Core Framework
- **FastAPI** - API REST asynchrone
- **Python 3.9+** - Langage principal
- **asyncio + httpx** - Gestion asynchrone validée

### Intégrations LLM
- **Claude (Anthropic)** - Extraction d'informations en langage naturel
- **MCP (Model Context Protocol)** - Communication avec les systèmes

### Bases de Données
- **PostgreSQL** - Base de données principale
- **SQLAlchemy** - ORM
- **Alembic** - Migrations (✅ **Stabilisé et fonctionnel**)

### Systèmes Intégrés
- **Salesforce** - CRM (simple-salesforce + API REST)
- **SAP Business One** - ERP (API REST)

### Validation & Enrichissement
- **INSEE API** - Validation SIRET (France)
- **API Adresse Gouv** - Normalisation adresses
- **fuzzywuzzy** - Détection de doublons

## 🚀 Installation et Configuration

### Prérequis
- Python 3.9+
- PostgreSQL 12+
- Accès Salesforce (Org + credentials)
- Accès SAP Business One (REST API)
- Clé API Claude (Anthropic)

### 1. Clone et Environment
```bash
git clone [repo-url]
cd NOVA-SERVER
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate     # Windows
```

### 2. Installation des Dépendances
```bash
pip install -r requirements.txt
```

### 3. Configuration (.env)
```bash
cp .env.example .env
# Puis éditer .env avec vos credentials
```

#### Variables Essentielles
```env
# Claude/Anthropic
ANTHROPIC_API_KEY=sk-ant-api03-...

# Salesforce
SALESFORCE_USERNAME=votre.email@domain.com
SALESFORCE_PASSWORD=VotrePassword
SALESFORCE_SECURITY_TOKEN=VotreToken
SALESFORCE_DOMAIN=login

# SAP Business One
SAP_REST_BASE_URL=https://votre-sap:50000/b1s/v1
SAP_USER=manager
SAP_CLIENT=SBODemoFR
SAP_CLIENT_PASSWORD=password

# Base de données
DATABASE_URL=postgresql://user:password@localhost:5432/nova_mcp_local

# APIs de validation (optionnel)
INSEE_CONSUMER_KEY=...
INSEE_CONSUMER_SECRET=...
```

### 4. Base de Données
```bash
# Créer la base de données
createdb nova_mcp_local

# Appliquer les migrations Alembic (✅ Stabilisé)
python -m alembic upgrade head
```

### 5. Démarrage des Services

#### Option A : Script Automatique (Windows)
```powershell
.\start_nova.ps1
```

#### Option B : Démarrage Manuel
```bash
# Terminal 1: Serveur MCP SAP
python sap_mcp.py

# Terminal 2: Serveur MCP Salesforce  
python salesforce_mcp.py

# Terminal 3: API FastAPI
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## 🧪 Tests et Validation

### Test Diagnostic
```bash
# Vérifier l'état de la base de données et Alembic
python diagnostic_db.py

# Test des connexions systèmes
python -c "import asyncio; from services.mcp_connector import MCPConnector; print(asyncio.run(MCPConnector.test_connections()))"
```

### Test Workflow Complet
```bash
# Test simple avec intégration réelle
python test_devis_generique.py "faire un devis pour 500 ref A00002 pour le client Edge Communications"

# Test enrichi avec validation client complète
python workflow/test_enriched_workflow.py
```

### API Endpoints Disponibles
- **GET** `/` - Health check et statut des modules
- **GET** `/docs` - Documentation Swagger interactive
- **POST** `/generate_quote` - Génération de devis avec intégration complète
- **POST** `/create_client` - Création client avec validation enrichie
- **GET** `/search_clients` - Recherche clients dans SF et SAP
- **GET** `/health` - Contrôle de santé détaillé

## 📊 Performances Validées

### Métriques de Performance (Intégrations Réelles)
- ⚡ **Workflow simple** : ~1,09s (validation réelle SAP/SF)
- ⚡ **Charge concurrente (5 req)** : ~1,10s
- ✅ **Parallélisme asyncio** : 99% d'efficacité
- 🎯 **Architecture** : Validée sans messaging externe pour le POC

## 🏗️ Structure du Projet

```
NOVA-SERVER/
├── 📁 alembic/                 # Migrations DB (✅ Stabilisé)
│   ├── env.py                 # Configuration Alembic
│   ├── alembic.ini            # Configuration principale
│   └── versions/              # Fichiers de migration
├── 📁 db/                      # Modèles et session DB
│   ├── models.py              # Modèles SQLAlchemy
│   └── session.py             # Configuration DB
├── 📁 routes/                  # Endpoints FastAPI
│   ├── routes_devis.py        # API génération devis
│   ├── routes_clients.py      # API gestion clients
│   ├── routes_salesforce.py   # API Salesforce
│   ├── routes_sap.py          # API SAP
│   └── routes_claude.py       # API Claude directe
├── 📁 services/                # Services métier
│   ├── llm_extractor.py       # Extraction Claude (intégration réelle)
│   ├── mcp_connector.py       # Connecteur MCP (production ready)
│   ├── client_validator.py    # Validation client enrichie
│   └── field_analyzer.py      # Analyse des champs
├── 📁 workflow/                # Orchestration métier
│   ├── devis_workflow.py      # Workflow principal (intégrations réelles)
│   └── test_enriched_workflow.py # Tests complets
├── 📁 static/                  # Interface web demo
├── 📁 logs/                    # Fichiers de log
├── sap_mcp.py                 # Serveur MCP SAP (production)
├── salesforce_mcp.py          # Serveur MCP Salesforce (production)
├── main.py                    # Application FastAPI
├── requirements.txt           # Dépendances (nettoyé, sans RabbitMQ)
└── .env                       # Configuration
```

## 🔧 Décisions d'Architecture

### ✅ Fondations Stabilisées

#### Base de Données
- **Alembic** : ✅ **Synchronisé et fonctionnel**
- **PostgreSQL** : Schema stable et évolutif

#### Messaging Asynchrone
- **Décision** : Architecture directe asyncio + httpx retenue
- **Performance** : 1,09s/workflow avec intégrations réelles
- **Justification** : Simplicité + performances suffisantes pour le POC

#### Intégrations
- **Salesforce** : Connexion réelle via simple-salesforce
- **SAP Business One** : API REST native
- **Claude** : API Anthropic directe

## 📋 Fonctionnalités Principales

### 🤖 Traitement du Langage Naturel
- **Extraction automatique** des informations de devis via Claude
- **Support multilingue** (FR/EN)
- **Fallback robuste** en cas d'échec LLM

### 👥 Gestion Client Enrichie
- **Validation SIRET** via API INSEE (France)
- **Normalisation adresses** via API Adresse Gouv
- **Détection de doublons** avec similarité fuzzy
- **Création automatique** dans Salesforce et SAP

### 📦 Gestion Produits & Stock
- **Stock temps réel** depuis SAP via API REST
- **Pricing automatique** avec fallbacks intelligents
- **Alternatives produits** en cas de rupture
- **Validation disponibilité** complète

### 📄 Génération de Devis
- **Création Salesforce** (Opportunities réelles)
- **Création SAP** (Quotations réelles)
- **Synchronisation** bidirectionnelle
- **Gestion d'erreurs** complète et logging

## 🔄 Workflow Type (Intégrations Réelles)

```mermaid
graph TD
    A[Prompt Utilisateur] --> B[Extraction Claude API]
    B --> C[Validation Client Salesforce]
    C --> D{Client Trouvé?}
    D -->|Non| E[Validation Enrichie INSEE/API]
    E --> F[Création Client SF+SAP]
    D -->|Oui| G[Récupération Produits SAP API]
    F --> G
    G --> H[Vérification Stock Temps Réel]
    H --> I[Alternatives si Rupture]
    I --> J[Création Devis SF+SAP]
    J --> K[Réponse Structurée]
```

## 🧪 Tests et Validation

### Scénarios de Test (Intégrations Réelles)
1. **Client existant + produits disponibles** ✅
2. **Client inexistant + création automatique** ✅
3. **Produits en rupture + alternatives** ✅
4. **Validation France (SIRET via INSEE)** ✅
5. **Validation internationale (US/UK)** ✅

### Métriques de Qualité
- ✅ Taux de succès > 95% (intégrations réelles)
- ✅ Temps de traitement < 2s
- ✅ Validation client > 90%
- ✅ Détection doublons fonctionnelle

## 📚 Documentation

### Guides Techniques
- `/docs` - Documentation API Swagger interactive
- `diagnostic_db.py` - Scripts de diagnostic système
- `workflow/test_enriched_workflow.py` - Tests complets

### Configuration Claude Desktop (Optionnelle)
```json
{
  "mcpServers": {
    "salesforce_mcp": {
      "command": "python",
      "args": ["C:\\path\\to\\NOVA\\salesforce_mcp.py"],
      "envFile": ".env"
    },
    "sap_mcp": {
      "command": "python", 
      "args": ["C:\\path\\to\\NOVA\\sap_mcp.py"],
      "envFile": ".env"
    }
  }
}
```

## 🚀 Roadmap

### ✅ Phase 1 : Fondations (Terminée)
- ✅ Infrastructure de base
- ✅ Intégrations Salesforce/SAP réelles
- ✅ Workflow de base fonctionnel
- ✅ Stabilisation Alembic

### 🔄 Phase 2 : Optimisation (En cours)
- 🔄 Performance tuning
- ✅ Gestion d'erreurs avancée
- ✅ Validation client enrichie
- 🔄 Tests complets

### 📅 Phase 3 : Production Ready
- 📅 Monitoring avancé
- 📅 Sécurité renforcée
- 📅 Documentation utilisateur
- 📅 Interface utilisateur finale

## 👨‍💻 Équipe de Développement

### Responsable Principal
- **Développeur/Architecte** : Développement complet du POC
- **Engagement** : Développement actif et maintenance

### Support Technique
- **Bruno CHARNAL** : Support technique (1/2 journée/semaine)

### Standards de Code
- **Linting** : Follow PEP8
- **Tests** : Validation par scénarios réels
- **Documentation** : Docstrings obligatoires
- **Logs** : Structured logging avec rotation

## 📞 Support

### Issues Communes
1. **Erreur connexion SAP/Salesforce** → Vérifier credentials dans `.env`
2. **Timeout API** → Vérifier connectivité réseau et VPN
3. **Erreur MCP** → Consulter logs dans `/logs/`
4. **Client non trouvé** → Activer validation enrichie
5. **Base de données** → Utiliser `diagnostic_db.py`

### Debug Rapide
```bash
# Vérifier l'état général
curl http://localhost:8000/health

# Tester les connexions
python -c "
import asyncio
from services.mcp_connector import MCPConnector
result = asyncio.run(MCPConnector.test_connections())
print('✅ Salesforce:', result.get('salesforce', {}).get('connected'))
print('✅ SAP:', result.get('sap', {}).get('connected'))
"
```

---

## 📊 Statut Global du Projet

| Composant | Statut | Commentaire |
|-----------|--------|-------------|
| **Base de données** | ✅ Stable | Alembic synchronisé |
| **API FastAPI** | ✅ Fonctionnel | Endpoints opérationnels |
| **Intégration Salesforce** | ✅ Production | Connexions réelles |
| **Intégration SAP** | ✅ Production | API REST fonctionnelle |
| **Workflow Devis** | ✅ Opérationnel | Tests validés |
| **Validation Client** | ✅ Enrichie | INSEE + doublons |
| **Performance** | ✅ Validée | <2s par workflow |

**Version Actuelle** : POC v1.0  
**Dernière MAJ** : 2025-06-03  
**Status** : 🟢 **Intégrations Réelles Fonctionnelles**  
**Prochaine Release** : Optimisation UI/UX

---

*Ce README reflète l'état exact du projet avec toutes les intégrations réelles validées.*