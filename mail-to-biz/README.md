# Mail-to-Biz - Plateforme Intelligente de Gestion des Devis

## Vue d'ensemble

Mail-to-Biz est une plateforme de traitement intelligent des demandes de devis par email. Elle automatise le processus complet depuis la réception d'un email jusqu'à la création d'un devis SAP Business One, en passant par l'analyse IA, l'identification du client, la recherche d'articles et la gestion des prix.

## Fonctionnalités Principales

### 1. Intégration Microsoft Graph (Office 365)
- **Connexion en temps réel** à la boîte mail Office 365 via Microsoft Graph API
- **Mode Démo / Mode Live** : Basculer entre données mockées et emails réels
- Récupération automatique des emails avec pagination
- Gestion des pièces jointes (PDF, Excel)
- Marquage des emails comme lus/non lus

### 2. Analyse Intelligente par IA (Claude/OpenAI)
- **Classification automatique** des emails :
  - `QUOTE_REQUEST` : Demande de devis
  - `INFORMATION` : Email informatif
  - `OTHER` : Autre type d'email
- **Extraction de données structurées** :
  - Nom du client et coordonnées
  - Liste des produits demandés (référence, quantité, description)
  - Délais de livraison et urgence
  - Notes et commentaires
- **Niveau de confiance** : `high`, `medium`, `low`
- Analyse des pièces jointes PDF pour extraction de tableaux de produits

### 3. Intégration SAP Business One
- **Connexion directe** à SAP B1 via Service Layer REST API
- **Gestion des clients** (Business Partners) :
  - Recherche par nom ou email
  - Création automatique si inexistant
  - Génération automatique du CardCode
- **Gestion des articles** (Items) :
  - Recherche par code ou description
  - Création automatique avec prix obligatoire
  - Intégration des tarifs fournisseurs
- **Création de devis** (Sales Quotations) :
  - Génération automatique depuis les emails
  - Calcul des prix et totaux
  - Traçabilité (référence email dans NumAtCard)

### 4. Base de Données Tarifs Fournisseurs
- **Indexation automatique** des fichiers Excel/PDF dans `C:\Users\PPZ\RONDOT`
- **Recherche rapide** par référence produit
- **Création d'articles SAP** avec prix fournisseur si article inexistant
- Base SQLite locale pour performance optimale

### 5. Interface Utilisateur Moderne
- **Dashboard responsive** avec React + TypeScript + Tailwind CSS
- **Composants shadcn-ui** pour une UI cohérente
- **Workflow en 3 étapes** :
  1. **Inbox** : Liste des emails avec badges de classification
  2. **Summary** : Résumé du devis avec données extraites
  3. **Validation** : Validation finale et création SAP
- **Mode clair/sombre** automatique
- **Notifications** en temps réel

## Architecture Technique

### Stack Frontend
- **React 18** avec TypeScript
- **Vite** pour le build et hot-reload
- **Tailwind CSS** + **shadcn-ui** pour le design
- **Tanstack Query** pour la gestion du state et cache
- **Lucide React** pour les icônes

### Stack Backend
- **FastAPI** (Python) pour l'API REST
- **HTTPX** pour les appels API asynchrones
- **Pydantic** pour la validation des données
- **SQLite** pour la base de tarifs fournisseurs
- **PyMuPDF** pour l'extraction PDF
- **OpenPyXL** pour le parsing Excel

### Services Backend

#### `services/graph_service.py`
Service Microsoft Graph avec gestion du token OAuth2 :
- Token caching avec buffer de 5 min avant expiration
- Récupération des emails avec filtres OData
- Téléchargement des pièces jointes

#### `services/email_analyzer.py`
Service d'analyse IA des emails :
- Classification rapide par règles (pré-filtrage)
- Analyse complète par LLM (Claude Sonnet 4.5)
- Extraction structurée des données de devis
- Parsing des pièces jointes PDF

#### `services/sap_business_service.py`
Service SAP Business One :
- Gestion de session avec auto-reconnexion
- CRUD Business Partners
- CRUD Items avec pricing
- Création de Sales Quotations
- Filtres OData pour recherche

#### `services/supplier_tariffs_db.py`
Base de données tarifs fournisseurs :
- Indexation automatique des fichiers
- Recherche fulltext par référence
- Caching pour performance

## API Endpoints

### Microsoft Graph
```
GET  /api/graph/test-connection          # Test connexion Graph API
GET  /api/graph/emails                   # Liste emails (params: top, skip, unread_only)
GET  /api/graph/emails/{id}              # Email complet avec body
GET  /api/graph/emails/{id}/attachments  # Liste pièces jointes
GET  /api/graph/emails/{id}/attachments/{att_id}/content  # Contenu pièce jointe
POST /api/graph/emails/{id}/analyze      # Analyse IA de l'email
GET  /api/graph/emails/{id}/analysis     # Résultat d'analyse (cache)
```

### SAP Business One
```
GET  /api/sap/health                     # Test connexion SAP
POST /api/sap/items/search               # Recherche d'articles
POST /api/sap/items/price                # Prix d'un article
POST /api/sap/partners/search            # Recherche client
POST /api/sap/partners/create            # Création client
POST /api/sap/quotations/create          # Création devis
POST /api/sap/quotations/from-email      # Devis complet depuis email (orchestration)
```

### Tarifs Fournisseurs
```
POST /api/supplier-tariffs/index         # Lance l'indexation
GET  /api/supplier-tariffs/search?q=...  # Recherche produit
GET  /api/supplier-tariffs/stats         # Statistiques base
```

## Configuration

### Variables d'environnement (.env)

#### Microsoft Graph (Office 365)
```bash
MS_TENANT_ID=<Azure AD Tenant ID>
MS_CLIENT_ID=<Azure App Registration Client ID>
MS_CLIENT_SECRET=<Azure App Secret>
MS_MAILBOX_ADDRESS=<Email address to monitor>
```

#### SAP Business One
```bash
SAP_REST_BASE_URL=https://<server>:<port>/b1s/v1
SAP_USER_RONDOT=<SAP username>
SAP_CLIENT_RONDOT=<SAP company database>
SAP_CLIENT_PASSWORD_RONDOT=<SAP password>
```

#### IA (Claude/OpenAI)
```bash
ANTHROPIC_API_KEY=<Claude API key>
ANTHROPIC_MODEL=claude-3-7-sonnet-20250219
OPENAI_API_KEY=<OpenAI API key>
OPENAI_MODEL=gpt-4o
```

#### Tarifs Fournisseurs
```bash
SUPPLIER_TARIFF_FOLDER=C:\Users\PPZ\RONDOT
DATABASE_URL=postgresql://...  # Base principale
```

### Permissions Azure AD

L'application Azure AD doit avoir les permissions suivantes :
- `Mail.Read` (Application permission)
- `User.Read` (Delegated permission - optionnel)

## Installation et Démarrage

### Prérequis
- **Node.js 18+** et npm
- **Python 3.10+**
- **PostgreSQL** (pour la base principale)
- **SAP Business One** avec Service Layer activé

### Installation Frontend

```bash
cd mail-to-biz
npm install
npm run dev
```

L'interface sera accessible sur `http://localhost:5173`

### Installation Backend

```bash
# À la racine du projet NOVA-SERVER
pip install -r requirements.txt

# Lancer le serveur
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Le backend sera accessible sur `http://localhost:8000`

### Indexation des Tarifs Fournisseurs

```bash
# Lancer l'indexation via API
curl -X POST http://localhost:8000/api/supplier-tariffs/index
```

Ou depuis l'interface web (bouton d'administration).

## Workflow Complet

```
1. Email reçu sur devis@rondot-poc.itspirit.ovh
   ↓
2. Récupération via Microsoft Graph API
   ↓
3. Analyse IA (Claude) :
   - Classification (QUOTE_REQUEST ?)
   - Extraction : client, produits, quantités
   ↓
4. Recherche/Création Client dans SAP :
   - Recherche par nom ou email
   - Si inexistant → création automatique
   ↓
5. Pour chaque produit :
   a. Recherche dans SAP Items
   b. Si inexistant → Recherche dans tarifs fournisseurs
   c. Si trouvé avec prix → Création Item dans SAP
   ↓
6. Création Sales Quotation dans SAP :
   - Lignes avec ItemCode + prix
   - Commentaires avec ID email source
   - Calcul totaux automatique
   ↓
7. Retour DocEntry à l'utilisateur
```

## Structure du Projet

```
mail-to-biz/
├── src/
│   ├── components/
│   │   ├── EmailList.tsx          # Liste des emails
│   │   ├── QuoteSummary.tsx       # Résumé du devis
│   │   ├── ValidationPanel.tsx    # Panel de validation
│   │   └── ui/                    # Composants shadcn-ui
│   ├── hooks/
│   │   ├── useEmails.ts           # Hook récupération emails
│   │   └── useEmailMode.ts        # Hook mode Demo/Live
│   ├── lib/
│   │   ├── graphApi.ts            # Client API Graph
│   │   └── preSapNormalizer.ts    # Normalisation données SAP
│   ├── pages/
│   │   └── Index.tsx              # Page principale
│   └── types/
│       └── email.ts               # Types TypeScript

services/
├── graph_service.py               # Service Microsoft Graph
├── email_analyzer.py              # Service analyse IA
├── sap_business_service.py        # Service SAP B1
├── supplier_tariffs_db.py         # Base tarifs fournisseurs
├── file_parsers.py                # Parsers PDF/Excel
└── llm_extractor.py               # Service LLM générique

routes/
├── routes_graph.py                # Routes API Graph
├── routes_sap_business.py         # Routes API SAP
└── routes_supplier_tariffs.py     # Routes tarifs fournisseurs
```

## Développement

### Lancer en mode développement

**Frontend** (hot-reload) :
```bash
cd mail-to-biz
npm run dev
```

**Backend** (auto-reload) :
```bash
uvicorn main:app --reload
```

### Tests

```bash
# Frontend
npm run test

# Backend (depuis la racine)
pytest tests/
```

### Build de Production

```bash
cd mail-to-biz
npm run build
```

Les fichiers buildés seront dans `mail-to-biz/dist/`

## Sécurité

- **Tokens OAuth2** stockés en mémoire uniquement (pas de localStorage)
- **Credentials SAP** en variables d'environnement (.env)
- **HTTPS** obligatoire pour Microsoft Graph
- **SSL désactivé** pour SAP (environnement de développement uniquement)
- **API Key** pour les endpoints sensibles

## Performance

- **Token caching** Microsoft Graph (évite reconnexions)
- **Session caching** SAP B1 (20 min de validité)
- **SQLite FTS5** pour recherche rapide tarifs fournisseurs
- **Lazy loading** des emails (pagination)
- **React.memo** pour éviter re-renders inutiles

## Limitations Connues

1. **Parser tarifs fournisseurs** : Extraction des références/prix à améliorer
2. **Pièces jointes >4MB** : Non supportées actuellement
3. **Multidevise** : Seul EUR supporté pour l'instant
4. **Stock SAP** : Articles créés sans gestion de stock (InventoryItem: tNO)

## Roadmap

- [ ] Amélioration du parser tarifs fournisseurs (extraction références)
- [ ] Support multidevise (USD, GBP, etc.)
- [ ] Gestion des remises clients SAP
- [ ] Export PDF du devis
- [ ] Envoi automatique du devis par email
- [ ] Dashboard analytics (emails traités, taux de conversion)
- [ ] Webhooks pour notifications temps réel
- [ ] Support des achats (Purchase Quotations)

## Support et Contact

Pour toute question ou problème :
- **Email** : support@itspirit.ovh
- **Documentation SAP** : https://help.sap.com/docs/SAP_BUSINESS_ONE
- **API Microsoft Graph** : https://learn.microsoft.com/en-us/graph/

## Licence

Propriétaire - ITSpirit © 2025

---

**Version actuelle** : 1.0.0
**Dernière mise à jour** : 2026-02-06
