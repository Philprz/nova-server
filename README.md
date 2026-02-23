# NOVA-SERVER - Plateforme Intelligente de Gestion Commerciale

**Statut : 🟢 OPÉRATIONNEL** | **Version : 2.8.0** | **Dernière MAJ : 20/02/2026**

## 🎯 Vue d'Ensemble

NOVA-SERVER est une plateforme complète d'automatisation des processus commerciaux qui combine Intelligence Artificielle, intégrations ERP/CRM et interfaces modernes pour transformer la gestion des devis, clients et produits.

### Philosophie du Projet

NOVA transforme les processus manuels chronophages en workflows intelligents automatisés :

- **De l'email au devis SAP** en quelques clics (Mail-to-Biz)
- **Du langage naturel à l'action** grâce à l'IA conversationnelle (NOVA Assistant)
- **De la donnée dispersée à la vue unifiée** avec synchronisation SAP/Salesforce

## 🏗️ Architecture Globale

```
┌─────────────────────────────────────────────────────────────────────┐
│                         NOVA-SERVER (FastAPI)                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐    │
│  │  NOVA Assistant │  │  Mail-to-Biz    │  │ Quote Manager   │    │
│  │                 │  │                 │  │                 │    │
│  │ IA Conversation │  │ Email → Devis   │  │ SAP ↔ SF Sync  │    │
│  │ Claude 4.5      │  │ Microsoft Graph │  │ Unified View    │    │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘    │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    Services Partagés                          │   │
│  ├──────────────────────────────────────────────────────────────┤   │
│  │ • MCP Connectors (SAP + Salesforce)                          │   │
│  │ • Client Validator (INSEE, Pappers, Adresse Gouv)            │   │
│  │ • Product Search Engine (Local + SAP)                        │   │
│  │ • Supplier Tariffs Database (SQLite FTS5)                    │   │
│  │ • Price Engine (Calcul prix clients)                         │   │
│  │ • LLM Extractor (Claude/OpenAI)                              │   │
│  │ • Suggestion Engine (IA + Fuzzy Matching)                    │   │
│  │ • WebSocket Manager (Temps réel)                             │   │
│  │ • Progress Tracker (Suivi workflows)                         │   │
│  │ • Cache Manager (Redis)                                      │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                       │
└───────────────────────┬───────────────────────────────────────────┬─┘
                        │                                           │
            ┌───────────┴──────────┐                   ┌───────────┴──────────┐
            │   SAP Business One   │                   │     Salesforce       │
            │   Service Layer API  │                   │      REST API        │
            └──────────────────────┘                   └──────────────────────┘
                        │                                           │
            ┌───────────┴──────────┐                   ┌───────────┴──────────┐
            │  PostgreSQL (NOVA)   │                   │  Microsoft Graph     │
            │  Articles, Clients   │                   │  Office 365 Emails   │
            └──────────────────────┘                   └──────────────────────┘
```

## 📦 Modules Principaux

### 1. NOVA Assistant - Assistant IA Conversationnel

**Objectif :** Interface conversationnelle en langage naturel pour la génération de devis.

**Fonctionnalités :**

- 💬 Chat intelligent avec Claude Sonnet 4.5
- 🔍 Recherche automatique de clients et produits
- ✅ Validation intelligente des données (SIRET, adresses)
- 🎯 Suggestions contextuelles avec correspondance floue
- 📊 Suivi en temps réel via WebSocket
- 🚀 Création de devis SAP + Salesforce en une conversation

**Technologies :**

- Backend : FastAPI + Claude API
- Frontend : HTML/CSS/JS vanilla (nova_interface_final.html)
- Real-time : WebSocket
- Workflow : DevisWorkflow avec 8 étapes orchestrées

**Routes principales :**

```
GET  /api/assistant/interface          # Interface conversationnelle
POST /api/assistant/chat               # Chat avec NOVA
POST /api/assistant/workflow/create_quote  # Workflow complet devis
WS   /ws/assistant/{task_id}           # WebSocket progression
```

**Workflow de génération de devis :**

```
1. Analyse du prompt utilisateur (LLM)
   ↓
2. Extraction client + produits
   ↓
3. Validation client (INSEE/Pappers) + Suggestions si doublons
   ↓
4. Recherche produits SAP (code/nom) + Suggestions
   ↓
5. Calcul prix clients (PriceEngine)
   ↓
6. Création devis SAP (Sales Quotation)
   ↓
7. Synchronisation Salesforce (Opportunity + Quote)
   ↓
8. Retour DocEntry + Lien Salesforce
```

---

### 2. Mail-to-Biz - Email Automatisé → Devis SAP

**Objectif :** Transformer automatiquement les emails de demande de devis en devis SAP Business One.

**Fonctionnalités :**

- 📧 Récupération emails Office 365 via Microsoft Graph
- 🤖 Analyse IA : Classification + Extraction données (Claude)
- 👥 Identification/Création automatique clients dans SAP
- 📦 Recherche articles SAP + Création si inexistant (avec tarifs fournisseurs)
- 💰 Prix automatiques depuis tarifs fournisseurs
- 📄 Parsing pièces jointes PDF/Excel (PyMuPDF)
- 🎨 Interface React moderne avec mode Démo/Live

**Technologies :**

- **Frontend :** React 18 + TypeScript + Vite + Tailwind CSS + shadcn-ui
- **Backend :** services/graph_service.py, email_analyzer.py, sap_business_service.py
- **IA :** Claude Sonnet 4.5 pour classification et extraction
- **Tarifs :** SQLite FTS5 (supplier_tariffs_db.py)

**Routes principales :**

```
# Microsoft Graph
GET  /api/graph/emails                 # Liste emails
GET  /api/graph/emails/{id}            # Email complet
POST /api/graph/emails/{id}/analyze    # Analyse IA

# SAP Business One
GET  /api/sap/health                   # Test connexion
POST /api/sap/items/search             # Recherche articles
POST /api/sap/partners/search          # Recherche clients
POST /api/sap/quotations/from-email    # Création devis complet

# Tarifs Fournisseurs
POST /api/supplier-tariffs/index       # Indexation fichiers
GET  /api/supplier-tariffs/search      # Recherche produits
```

**Workflow Email → Devis SAP :**

```
1. Email reçu sur devis@rondot-poc.itspirit.ovh
   ↓
2. Récupération via Microsoft Graph API
   ↓
3. Analyse IA :
   - Classification : QUOTE_REQUEST ?
   - Extraction : client, produits, quantités
   ↓
4. Recherche/Création Client SAP :
   - Recherche par nom/email
   - Création automatique si inexistant
   ↓
5. Pour chaque produit :
   a. Recherche dans SAP Items
   b. Si non trouvé → Recherche dans tarifs fournisseurs
   c. Si trouvé avec prix → Création Item SAP
   ↓
6. Création Sales Quotation SAP :
   - Lignes avec ItemCode + Prix
   - Traçabilité (référence email)
   ↓
7. Retour DocEntry SAP
```

**Frontend (React SPA) :**

- Accessible sur `/mail-to-biz`
- Composants : EmailList, QuoteSummary, QuoteValidation
- Hooks : useEmails, useEmailMode (Demo/Live)
- API Client : graphApi.ts

#### 2.1 Matching Intelligent Client/Produit ⭐ NOUVEAU (v2.5.0)

**Objectif :** Identifier automatiquement clients et produits SAP avec matching multi-stratégies intelligent et apprentissage automatique.

**Fonctionnalités :**

- 🎯 **Matching clients** par domaine email + nom (fuzzy matching avec blacklist)
- 📦 **Matching produits intelligent** avec cascade 4 niveaux
- 🧠 **Apprentissage automatique** des codes produits externes (fournisseurs)
- 📞 **Filtrage intelligent** des numéros de téléphone et mots-clés
- 🔄 **Pagination SAP** pour charger jusqu'à 1000 clients / 2000 produits
- ⚡ **Cache 2h** pour performances optimales (SQLite local)
- 🗃️ **Base d'apprentissage** SQLite avec historique des mappings

**Cascade Intelligente Produits (4 niveaux) :**

```
1. Exact ItemCode Match (Score 100)
   └─ Recherche code exact dans SAP Items cache

2. Learned Mapping (Score 95)
   └─ Lookup dans product_code_mapping table
   └─ Utilise mappings validés précédemment

3. Fuzzy Match ItemName (Score ≥ 90 pour auto-validation)
   └─ difflib.SequenceMatcher sur descriptions
   └─ Seuil 90% requis pour auto-apprentissage

4. Register as PENDING (Score 0)
   └─ Enregistre dans DB pour validation manuelle
   └─ Permet création produit SAP ultérieure
```

**Stratégies de matching clients :**

| Type              | Stratégie               | Score | Exemple                                   |
| ----------------- | ------------------------ | ----- | ----------------------------------------- |
| **Client**  | Domaine email exact      | 95    | chq@saverglass.com → SAVERGLASS          |
| **Client**  | Domaine + Nom dans texte | 98    | Email saverglass.com + texte "SAVERGLASS" |
| **Client**  | Nom exact dans texte     | 90    | "SAVERGLASS" dans email                   |
| **Client**  | Nom compact match        | 88    | "MarmaraCam" → "MARMARA CAM"              |
| **Client**  | Fuzzy match nom          | 70-85 | "SAVER GLASS" ~ "SAVERGLASS"              |

**Stratégies de matching produits :**

| Niveau    | Stratégie                         | Score | Exemple                                |
| --------- | ---------------------------------- | ----- | -------------------------------------- |
| **1** | ItemCode exact SAP                 | 100   | "2323060165" dans Items cache         |
| **2** | Mapping appris (VALIDATED)         | 95    | "HST-117-03" → ItemCode validé       |
| **3** | Fuzzy ItemName (≥ 90%)           | 90-99 | "PISTON 509" ~ "PISTON 509-210-04"     |
| **4** | Inconnu → PENDING apprentissage | 0     | "TRI-037" → Enregistré pour création |

**Extraction améliorée codes produits (4 patterns) :**

```regex
Pattern 1: \b(\d{6,})\b                  # Codes numériques longs (ex: 2323060165)
Pattern 2: \b([A-Z]{1,4}-[A-Z0-9-]+)\b   # Codes avec tirets (ex: HST-117-03)
Pattern 3: \b([A-Z]{1,4}\d{3,}[A-Z0-9]*)\b  # Codes sans tirets (ex: C3156305RS)
Pattern 4: (?:SHEPPEE\s+)?CODE:\s*([A-Z0-9-]+)  # Format "CODE: XXX"
```

**Blacklist mots communs** (anti-faux positifs) :

```python
_BLACKLIST_WORDS = {
    'devis', 'prix', 'price', 'quote', 'demande', 'request', 'offre',
    'bonjour', 'hello', 'merci', 'thanks', 'cordialement', 'regards'
}
```

**Fichiers :**

- `services/email_matcher.py` - Service matching intelligent (~600 lignes)
- `services/product_mapping_db.py` - Base apprentissage SQLite (300 lignes)
- Intégration dans `routes/routes_graph.py` (analyse emails)

#### 2.2 Détection Doublons (30 jours) ⭐ NOUVEAU (v2.4.0)

**Objectif :** Éviter le traitement multiple des mêmes demandes de devis.

**Fonctionnalités :**

- 🔍 **3 types de détection** : strict, probable, possible
- 📅 **Fenêtre 30 jours** (durée validité devis)
- 🗃️ **Base SQLite** avec historique traité
- 📊 **Statistiques** doublons prévenus

**Types de détection :**

```
STRICT (confidence 100%)
└─ Email ID identique déjà traité

PROBABLE (confidence 70-100%)
└─ Même client + 70% produits similaires (30 jours)

POSSIBLE (confidence 80-100%)
└─ Même expéditeur + sujet similaire 80% (30 jours)
```

**Table SQLite `processed_emails` :**

- email_id, sender_email, subject
- client_card_code, product_codes (JSON)
- processed_at, status (pending/completed/rejected)
- quote_id, sap_doc_entry

**Fichiers :**

- `services/duplicate_detector.py` - Service détection (320 lignes)
- Intégration automatique dans workflow analyse email

#### 2.3 Auto-Validation & Choix Multiples ⭐ NOUVEAU (v2.4.0)

**Objectif :** Valider automatiquement les matchs haute confiance, demander confirmation pour ambiguïtés.

**Fonctionnalités :**

- ✅ **Auto-validation** client score ≥ 95
- ✅ **Auto-validation** produits score = 100
- ⚠️ **Choix utilisateur** si plusieurs matches ou score < 95
- 🎯 **Recommandations** automatiques (meilleur score)

**Règles d'auto-validation :**

| Scénario                     | Condition             | Action                        |
| ----------------------------- | --------------------- | ----------------------------- |
| Client unique confiance haute | 1 client, score ≥ 95 | ✅ Validé automatiquement    |
| Client unique confiance basse | 1 client, score < 95  | ⚠️ Confirmation utilisateur |
| Clients multiples             | 2+ clients matchés   | ⚠️ Choix utilisateur        |
| Produits codes exacts         | Tous score = 100      | ✅ Validés automatiquement   |
| Produits ambigus              | 1+ score < 100        | ⚠️ Choix utilisateur        |
| Rien trouvé                  | Aucun match SAP       | ❌ Création nécessaire      |

**Endpoints API :**

```
GET  /api/graph/emails/{id}/validation-status
     → Statut validation (ready_for_quote_generation?)

POST /api/graph/emails/{id}/confirm-client
     → Utilisateur confirme client choisi

POST /api/graph/emails/{id}/confirm-products
     → Utilisateur confirme produits choisis
```

**Réponse enrichie :**

```json
{
  "client_matches": [...],      // Tous les clients matchés
  "product_matches": [...],     // Tous les produits matchés
  "client_auto_validated": true,
  "products_auto_validated": false,
  "requires_user_choice": true,
  "user_choice_reason": "5 clients possibles - Choix requis"
}
```

#### 2.4 Apprentissage Automatique & Validation Produits ⭐ NOUVEAU (v2.5.0)

**Objectif :** Système intelligent d'apprentissage automatique pour codes produits externes (fournisseurs) avec validation et création dans SAP B1.

**Problématique :**

Les emails contiennent souvent des références fournisseurs (ex: "HST-117-03", "TRI-037") qui n'existent pas dans SAP. Le système doit :
1. Détecter ces codes inconnus
2. Tenter de les matcher intelligemment
3. Apprendre les associations validées
4. Permettre la création de nouveaux produits SAP

**Architecture Apprentissage :**

```
┌─────────────────────────────────────────────────────────────┐
│                Email avec Codes Fournisseurs                 │
│  "SHEPPEE CODE: HST-117-03 - PUSHER BLADE - 50 pcs"         │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│            Extraction Codes (4 Patterns Regex)               │
│  → HST-117-03, TRI-037, C315-6305RS, etc.                   │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│              Cascade Intelligente 4 Niveaux                  │
│                                                               │
│  1️⃣ Exact Match ItemCode → Score 100 ✅                    │
│  2️⃣ Learned Mapping (DB) → Score 95 ✅                     │
│  3️⃣ Fuzzy Match Name (≥90%) → Score 90+ ✅                 │
│  4️⃣ Not Found → PENDING 🔄                                  │
└──────────────────┬──────────────────────────────────────────┘
                   │
       ┌───────────┴───────────┐
       │                       │
       ▼                       ▼
┌─────────────────┐   ┌──────────────────────────┐
│  Auto-Validated │   │  Manual Validation       │
│  (Score ≥ 90)   │   │  Dashboard React         │
│  ✅ Utilisé     │   │  - Associer à existant   │
│  directement    │   │  - Créer dans SAP        │
│                 │   │  - Rejeter               │
└─────────────────┘   └──────────┬───────────────┘
                                 │
                                 ▼
                    ┌──────────────────────────┐
                    │  SAP Product Creator     │
                    │  POST /Items             │
                    │  → ItemCode créé         │
                    └──────────┬───────────────┘
                               │
                               ▼
                    ┌──────────────────────────┐
                    │  Validation Mapping      │
                    │  UPDATE status=VALIDATED │
                    │  → Apprentissage réussi  │
                    └──────────────────────────┘
```

**Base de Données Apprentissage (`product_code_mapping`) :**

```sql
CREATE TABLE product_code_mapping (
    external_code TEXT NOT NULL,           -- "HST-117-03" (code fournisseur)
    external_description TEXT,             -- "SIZE 3 PUSHER BLADE CARBON"
    supplier_card_code TEXT NOT NULL,      -- "C0249" (SHEPPEE)
    matched_item_code TEXT,                -- "IM30043" (SAP) ou NULL
    match_method TEXT,                     -- "EXACT", "FUZZY_NAME", "MANUAL", "PENDING"
    confidence_score REAL,                 -- 0-100
    status TEXT DEFAULT 'PENDING',         -- "PENDING", "VALIDATED", "REJECTED"
    created_at TIMESTAMP DEFAULT NOW,
    last_used TIMESTAMP,
    use_count INTEGER DEFAULT 1,

    PRIMARY KEY (external_code, supplier_card_code)
);
```

**Statistiques Tracking :**

- Total mappings enregistrés
- Mappings validés vs en attente
- Taux de réussite par méthode (EXACT, FUZZY, MANUAL)
- Top codes fournisseurs les plus utilisés
- Historique validations par utilisateur

**Dashboard React Validation (`/mail-to-biz/products/validation`) :**

**Fonctionnalités Interface :**

```tsx
// Statistiques temps réel
┌─────────────────────────────────────────────────┐
│  📊 STATISTIQUES PRODUITS                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │    35    │  │    12    │  │    47    │      │
│  │ En attente│  │ Validés  │  │  Total   │      │
│  └──────────┘  └──────────┘  └──────────┘      │
└─────────────────────────────────────────────────┘

// Liste produits en attente
┌─────────────────────────────────────────────────────────────────┐
│  Code Externe  │ Description         │ Fournisseur │ Actions    │
├────────────────┼────────────────────┼─────────────┼────────────┤
│  HST-117-03    │ PUSHER BLADE       │ SHEPPEE     │ [Associer] │
│                │                     │             │ [Créer]    │
│                │                     │             │ [Rejeter]  │
├────────────────┼────────────────────┼─────────────┼────────────┤
│  TRI-037       │ LIFT ROLLER STUD   │ SHEPPEE     │ [Associer] │
│                │                     │             │ [Créer]    │
│                │                     │             │ [Rejeter]  │
└─────────────────────────────────────────────────────────────────┘
```

**Actions Utilisateur :**

1. **[Associer]** - Recherche et association à produit SAP existant
   - Modal avec recherche live dans 23,571 produits SAP
   - Affichage ItemCode + ItemName
   - Validation immédiate du mapping

2. **[Créer]** - Création nouveau produit dans SAP
   - Code SAP auto-généré (`RONDOT-{external_code}`, max 20 chars)
   - Formulaire pré-rempli (nom, description)
   - Sélection groupe produits (100, 105, 110)
   - Flags : Achetable / Vendable / Stockable
   - POST `/Items` vers SAP B1 Service Layer

3. **[Rejeter]** - Supprimer le mapping
   - Produit non pertinent ou erreur d'extraction
   - Suppression définitive de la base

**Service Création Produits SAP (`sap_product_creator.py`) :**

**Méthodes principales :**

```python
async def create_product(
    self,
    item_code: str,              # Code SAP (20 chars max)
    item_name: str,              # Nom produit (100 chars max)
    item_group: str = "100",     # Groupe produits
    purchase_item: bool = True,
    sales_item: bool = True,
    inventory_item: bool = True,
    external_code: Optional[str] = None,
    supplier_card_code: Optional[str] = None
) -> Dict[str, Any]:
    """
    Crée un produit dans SAP B1 et met à jour le mapping local

    POST /Items
    {
        "ItemCode": "RONDOT-HST11703",
        "ItemName": "SIZE 3 PUSHER BLADE CARBON",
        "ItemsGroupCode": 100,
        "PurchaseItem": "tYES",
        "SalesItem": "tYES",
        "InventoryItem": "tYES"
    }

    → Retourne ItemCode créé + MAJ cache local
    → Valide mapping (status=VALIDATED)
    """

def generate_item_code(
    self,
    external_code: str,
    prefix: str = "RONDOT"
) -> str:
    """
    Génère code SAP depuis code externe

    "HST-117-03" → "RONDOT-HST11703" (tirets supprimés, max 20 chars)
    """

async def bulk_create_from_pending(
    self,
    supplier_card_code: Optional[str] = None,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Création en masse depuis PENDING

    → Utile pour importer catalogue fournisseur complet
    """
```

**Routes API Validation Produits :**

```python
GET  /api/products/pending
     → Liste produits PENDING (avec filtres fournisseur, limite)

POST /api/products/validate
     → Associer code externe à ItemCode SAP existant
     Body: {
         external_code: "HST-117-03",
         supplier_card_code: "C0249",
         matched_item_code: "IM30043"
     }

POST /api/products/create
     → Créer nouveau produit dans SAP
     Body: {
         external_code: "HST-117-03",
         external_description: "PUSHER BLADE",
         supplier_card_code: "C0249",
         new_item_code: "RONDOT-HST11703",  # Optionnel
         item_name: "SIZE 3 PUSHER BLADE CARBON",
         item_group: "100",
         purchase_item: true,
         sales_item: true,
         inventory_item: true
     }
     → Retourne ItemCode créé

POST /api/products/bulk-create
     → Création en masse depuis PENDING
     Body: {
         supplier_card_code: "C0249",  # Optionnel
         limit: 50
     }

GET  /api/products/mapping/statistics
     → Statistiques globales
     {
         total: 47,
         validated: 12,
         pending: 35,
         exact_matches: 8,
         fuzzy_matches: 3,
         manual_matches: 1
     }

DELETE /api/products/mapping/{external_code}
       → Supprimer mapping (avec supplier_card_code en query param)

GET  /api/products/search?query={query}&limit={limit}
     → Recherche produits SAP (pour modal association)
```

**Workflow Complet Exemple (PDF Marmara Cam - 28 produits SHEPPEE) :**

```
1. Email reçu avec PDF "Sheppee International Ltd_20250701.pdf"
   ↓
2. Extraction PDF → 28 codes SHEPPEE détectés
   ↓
3. Matching intelligent (cascade 4 niveaux)
   → 0 exact matches (codes jamais vus)
   → 0 learned mappings (première fois)
   → 0 fuzzy matches (descriptions trop génériques)
   → 35 codes enregistrés PENDING (28 + 7 variantes détectées)
   ↓
4. Dashboard affiche 35 produits en attente
   ↓
5. Utilisateur pour chaque produit :

   Option A: [Associer]
   - Recherche "PUSHER BLADE" dans SAP
   - Trouve "IM30043 - BLADE PUSHER 3"
   - Clique → Mapping validé
   - Prochaine occurrence "HST-117-03" → Auto-reconnu (Score 95)

   Option B: [Créer]
   - Code auto: "RONDOT-HST11703"
   - Nom: "SIZE 3 PUSHER BLADE CARBON"
   - Groupe: 100
   - [Créer dans SAP] → POST /Items
   - ItemCode créé: "RONDOT-HST11703"
   - Mapping validé

   Option C: [Rejeter]
   - Produit non pertinent
   - Supprimé de la base
   ↓
6. Statistiques mises à jour
   - Pending: 35 → 0
   - Validated: 0 → 32
   - Rejected: 0 → 3
   ↓
7. Prochain email SHEPPEE
   → 32 codes auto-reconnus (Score 95) ✅
   → 0 validation manuelle requise 🎉
```

**Bénéfices :**

- ✅ **Apprentissage progressif** - Chaque validation enrichit la base
- ✅ **Zéro duplication** - Codes fournisseurs uniques par fournisseur
- ✅ **Traçabilité complète** - Historique de toutes les associations
- ✅ **Création SAP intégrée** - Pas de double saisie
- ✅ **Interface intuitive** - Dashboard React moderne
- ✅ **Performance** - Cache local SQLite (pas de requêtes SAP répétées)
- ✅ **Scalabilité** - Supporte des milliers de codes fournisseurs

**Fichiers créés :**

- `services/product_mapping_db.py` (300 lignes) - Base apprentissage
- `services/sap_product_creator.py` (300 lignes) - Création produits SAP
- `routes/routes_product_validation.py` (450 lignes) - API validation
- `mail-to-biz/src/pages/ProductValidation.tsx` (500 lignes) - Dashboard React

#### 2.5 Création Clients/Produits SAP ⭐ AMÉLIORÉ (v2.5.0)

**Objectif :** Créer automatiquement les clients et produits manquants dans SAP B1 (complété par système apprentissage v2.5.0).

**Fonctionnalités :**

- 🆕 **Création clients** avec données enrichies (email)
- 🆕 **Création produits** avec vérification fichiers fournisseurs
- ✅ **Validation données** avec Pydantic
- 🔍 **Vérification doublons** avant création
- 📝 **Traçabilité** source NOVA

**Workflow création client :**

```
1. Vérifier existence dans SAP
   ├─ Existe → Retourner CardCode
   └─ N'existe pas → Continuer

2. Formulaire pré-rempli (données email)

3. POST /api/sap/clients/create
   └─ Validation: nom, email, SIRET, adresse

4. Création dans SAP Business Partners
   └─ Retour CardCode créé
```

**Workflow création produit :**

```
1. Vérifier existence dans SAP Items
   ├─ Existe → Retourner ItemCode
   └─ N'existe pas → Continuer

2. Vérifier dans fichiers fournisseurs
   ├─ Trouvé → Enrichir données (prix, fournisseur)
   └─ Non trouvé → Alerte création manuelle

3. POST /api/sap/products/create
   └─ Validation: code, nom, prix, fournisseur

4. Création dans SAP Items
   └─ Retour ItemCode créé ou alerte manuel
```

**Endpoints création :**

```
# Clients
POST /api/sap/clients/create
GET  /api/sap/clients/check-exists/{card_name}

# Produits
POST /api/sap/products/create
GET  /api/sap/products/check-exists/{item_code}
GET  /api/sap/products/check-supplier-files/{item_code}

# Workflow automatique complet
POST /api/sap/workflow/check-and-create-if-needed
```

**Modèles de données :**

```python
# Création client
NewClientData(
    card_name: str,           # Obligatoire
    contact_email: str,
    phone: str,
    address: str,
    city: str,
    zip_code: str,
    country: str = "FR",
    siret: str,              # SIRET/TVA
    payment_terms: str = "30"
)

# Création produit
NewProductData(
    item_code: str,          # Obligatoire
    item_name: str,          # Obligatoire
    supplier_code: str,      # Fournisseur
    purchase_price: float,   # Prix achat
    sale_price: float,       # Prix vente
    manage_stock: bool = True
)
```

**Fichiers :**

- `services/sap_creation_service.py` - Service création (500+ lignes)
- `routes/routes_sap_creation.py` - API endpoints (380+ lignes)

#### 2.6 Webhook Microsoft Graph - Traitement Automatique 100% ⭐ NOUVEAU (v2.6.0)

**Objectif :** Traitement automatique en background des emails dès leur réception, sans intervention manuelle.

**Problématique résolue :**

Avant v2.6.0, l'utilisateur devait :
1. Cliquer "Traiter" pour chaque email (2-5 secondes)
2. Attendre le chargement de la boîte de réception (20-50 secondes)
3. Les emails étaient retraités à chaque visite (duplication travail)

**Solution v2.6.0 :**

Les emails sont maintenant **traités automatiquement en background** dès leur réception via webhook Microsoft Graph.

**Architecture Webhook :**

```
┌────────────────────────────────────────────────────────────┐
│ 1. Email arrive (Microsoft 365)                            │
│    └─> Microsoft Graph envoie notification push            │
└────────────────────┬───────────────────────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────────────────────┐
│ 2. NOVA reçoit notification                                │
│    POST /api/webhooks/notification                         │
│    └─> Extrait message_id                                  │
└────────────────────┬───────────────────────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────────────────────┐
│ 3. Traitement automatique background (async)               │
│    ├─> Récupération email + PDFs (100-500ms)              │
│    ├─> Analyse LLM (Claude/GPT-4) (1-3s)                  │
│    ├─> Matching SAP clients/produits (500ms-1s)           │
│    ├─> Enrichissement SAP (200-500ms)                     │
│    └─> Pricing automatique (200-800ms)                     │
└────────────────────┬───────────────────────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────────────────────┐
│ 4. Sauvegarde résultat (SQLite)                           │
│    └─> email_analysis.db (persistance complète)           │
└────────────────────┬───────────────────────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────────────────────┐
│ 5. Utilisateur se connecte                                 │
│    ├─> Email DÉJÀ traité                                  │
│    ├─> Inbox charge < 1 seconde                           │
│    ├─> Bouton "Synthèse" (pas "Traiter")                  │
│    └─> Affichage instantané (< 50ms)                      │
└────────────────────────────────────────────────────────────┘
```

**Fonctionnalités :**

- 🔔 **Notifications push** Microsoft Graph (temps réel)
- 🤖 **Traitement automatique** en background (FastAPI BackgroundTasks)
- 💾 **Persistance SQLite** (email_analysis.db)
- 🔄 **Renouvellement automatique** webhook (expire après 3 jours)
- 🔒 **Validation sécurisée** (clientState token)
- ⚡ **Performance optimale** (< 5 secondes traitement complet)
- 🎯 **Classification intelligente** (détection devis uniquement)

**Gains de Performance :**

| Métrique | Avant v2.6.0 | Après v2.6.0 | Gain |
|----------|--------------|--------------|------|
| **Chargement inbox** | 20-50 secondes | < 1 seconde | **-95%** |
| **Affichage synthèse** | 2-5 secondes | < 50 ms | **-99%** |
| **Actions manuelles** | 3 clics | 0 clic | **100% auto** |
| **Retraitement** | À chaque visite | Jamais | ✅ Résolu |

**Service Webhook (`services/webhook_service.py`) :**

```python
async def create_subscription(
    resource: str,
    change_type: str = "created",
    notification_url: str,
    client_state: str
) -> Dict[str, Any]:
    """
    Crée subscription webhook Microsoft Graph
    - Durée : 3 jours
    - Resource : users/{user_id}/mailFolders('Inbox')/messages
    - Change type : created (nouveaux emails uniquement)
    """

async def renew_subscription(subscription_id: str) -> Dict[str, Any]:
    """Renouvelle subscription avant expiration"""

def get_subscriptions_to_renew() -> list:
    """Liste subscriptions expirant dans < 24h"""
```

**Routes API Webhook :**

```
POST /api/webhooks/notification        # Reçoit notifications Microsoft
GET  /api/webhooks/subscriptions        # Liste subscriptions actives
GET  /api/webhooks/subscriptions/to-renew  # Subscriptions à renouveler
POST /api/webhooks/subscriptions/renew/{id}  # Renouveler subscription
DELETE /api/webhooks/subscriptions/{id}  # Supprimer subscription
```

**Base de Données :**

**Table `subscriptions` (webhooks.db) :**

```sql
CREATE TABLE subscriptions (
    id TEXT PRIMARY KEY,              -- Subscription ID Microsoft
    resource TEXT NOT NULL,           -- users/{id}/mailFolders('Inbox')/messages
    change_type TEXT NOT NULL,        -- "created"
    notification_url TEXT NOT NULL,   -- https://nova-rondot.itspirit.ovh/api/webhooks/notification
    expiration_datetime TEXT NOT NULL,
    client_state TEXT,                -- Token secret validation
    created_at TIMESTAMP,
    renewed_at TIMESTAMP,
    status TEXT DEFAULT 'active'
);
```

**Table `email_analysis` (email_analysis.db) :**

```sql
CREATE TABLE email_analysis (
    email_id TEXT PRIMARY KEY,
    subject TEXT,
    from_address TEXT,
    analysis_result TEXT,             -- JSON complet (LLM + SAP + Pricing)
    analyzed_at TIMESTAMP,
    is_quote_request BOOLEAN
);
```

**Configuration (.env) :**

```env
# Webhook Microsoft Graph
WEBHOOK_NOTIFICATION_URL=https://nova-rondot.itspirit.ovh/api/webhooks/notification
WEBHOOK_CLIENT_STATE=NOVA_WEBHOOK_SECRET_2026_aB3xY9zK7mN4qP2w
GRAPH_USER_ID=229aa9a1-2581-4ac1-ae1f-68273832e2e5
```

**Scripts de Gestion :**

```bash
# 1. Récupérer User ID (une fois)
python get_user_id.py

# 2. Enregistrer webhook (une fois)
python register_webhook.py

# 3. Renouveler webhook (avant expiration)
python renew_webhook.py
```

**Renouvellement Automatique (Windows Task Scheduler) :**

Le webhook expire après 3 jours. Pour automatiser le renouvellement :

1. Ouvrir **Planificateur de tâches** Windows
2. Créer tâche : `NOVA Webhook Renewal`
3. Déclencheur : Quotidien à 09:00
4. Action : `python renew_webhook.py`
5. Dossier : `C:\Users\PPZ\NOVA-SERVER`

**Workflow Complet Exemple :**

```
1. Email reçu à 09:00 sur devis@rondot-poc.itspirit.ovh
   ↓ (< 30 secondes)
2. Microsoft Graph notifie webhook NOVA
   ↓ (< 1 seconde)
3. NOVA extrait message_id et lance traitement background
   ↓ (2-5 secondes)
4. Traitement complet :
   - LLM : Classification + Extraction client/produits
   - SAP : Matching client (Saverglass score 97)
   - SAP : Matching produits (28 codes détectés)
   - Pricing : Calcul CAS 1-4 pour chaque produit
   ↓ (< 50ms)
5. Sauvegarde en DB (email_analysis.db)
   ↓
6. Utilisateur se connecte à 09:30
   ↓ (< 1 seconde)
7. Inbox affiche email avec bouton "Synthèse"
   ↓ (< 50ms)
8. Clic "Synthèse" → Affichage instantané complet
```

**Frontend Intelligence (useEmails.ts) :**

Le frontend a été modifié pour :

1. **Consulter DB d'abord** (GET /analysis) avant de lancer traitement
2. **Pré-analyse intelligente** : Vérifie DB pour tous les emails devis visibles
3. **Éviter duplication** : Si analyse existe en DB, réutilisation instantanée
4. **Bouton adaptatif** : "Synthèse" si traité, "Analyser" sinon

**Fichiers créés :**

- `services/webhook_service.py` (319 lignes) - Gestion subscriptions
- `routes/routes_webhooks.py` (386 lignes) - Endpoint webhook + auto-processing
- `services/email_analysis_db.py` (220 lignes) - Persistance SQLite
- `register_webhook.py` (104 lignes) - Script enregistrement
- `renew_webhook.py` (75 lignes) - Script renouvellement
- `get_user_id.py` (120 lignes) - Récupération User ID
- `WEBHOOK_CONFIGURATION_GUIDE.md` - Guide configuration complet
- `INSTRUCTIONS_WEBHOOK.txt` - Instructions étape par étape

**Fichiers modifiés :**

- `mail-to-biz/src/hooks/useEmails.ts` - Logique GET /analysis avant POST
- `mail-to-biz/src/components/EmailList.tsx` - Bouton "Synthèse" adaptatif
- `main.py` - Enregistrement routes webhook

**Documentation complète :**

- `WEBHOOK_CONFIGURATION_GUIDE.md` - Guide technique complet
- `INSTRUCTIONS_WEBHOOK.txt` - Instructions pas à pas
- `FIX_RELANCE_ET_LENTEUR_COMPLETE.md` - Explication technique fixes

**Bénéfices v2.6.0 :**

- ✅ **Zéro intervention manuelle** (100% automatique)
- ✅ **Réactivité temps réel** (< 30s réception → traitement)
- ✅ **Expérience utilisateur optimale** (< 1s chargement inbox)
- ✅ **Élimination retraitement** (persistance DB)
- ✅ **Traçabilité complète** (email_analysis.db)
- ✅ **Scalabilité** (traitement asynchrone non-bloquant)

---

#### 2.7 Persistance SAP Stricte - Architecture Quote Draft ⭐ NOUVEAU (v2.7.0)

**Objectif :** Garantir que toutes les requêtes SAP sont effectuées UNE SEULE FOIS lors de la réception email, avec persistance complète et ZERO requête SAP aux consultations ultérieures.

**Problématique résolue :**

Avant v2.7.0, le système effectuait potentiellement des requêtes SAP multiples :
- ❌ Requêtes SAP relancées à chaque ouverture de synthèse
- ❌ Pas de garantie d'idempotence stricte sur mail_id
- ❌ Métadonnées de recherche SAP non persistées
- ❌ Impossible de relancer recherche pour ligne isolée

**Solution v2.7.0 :**

Architecture avec **persistance stricte** selon spécifications techniques RONDOT.

**Nouveaux fichiers créés** (~1100 lignes) :

1. **`services/mail_processing_log_service.py`** (207 lignes)
   - Service logging structuré pour traçabilité complète
   - Table `mail_processing_log` avec 6 colonnes
   - Logs: WEBHOOK_RECEIVED, LLM_ANALYSIS_COMPLETE, SAP_CLIENT_SEARCH_COMPLETE, SAP_PRODUCTS_SEARCH_COMPLETE, PRICING_COMPLETE, QUOTE_DRAFT_CREATED

2. **`services/quote_repository.py`** (371 lignes)
   - Repository CRUD pour table `quote_draft`
   - UNIQUE constraint sur `mail_id` (idempotence)
   - Structure JSONB lines avec métadonnées SAP complètes
   - Méthodes: create_quote_draft(), get_quote_draft(), update_line_sap_data()

3. **`services/sap_client.py`** (232 lignes)
   - Centralisation de TOUS les appels SAP
   - Wrapper email_matcher + pricing_engine
   - Métadonnées complètes (query_used, timestamp, match_score)
   - Méthodes: search_client(), search_item(), get_item_price()

4. **`services/mail_processor.py`** (260 lignes)
   - Orchestrateur workflow mail-to-biz
   - 10 étapes séquentielles avec logs exhaustifs
   - Wrapper services existants (email_analyzer, email_matcher, pricing_engine)
   - Construit structure quote_draft stricte

5. **`services/retry_service.py`** (169 lignes)
   - Service relance recherche SAP pour ligne isolée
   - Update UNIQUEMENT la ligne concernée (pas de re-traitement)
   - Support retry automatique ou code manuel

6. **`routes/routes_mail.py`** (341 lignes)
   - 4 nouveaux endpoints API
   - POST /api/mail/incoming (traitement initial IDEMPOTENT)
   - GET /api/quote_draft/{id} (lecture seule ZERO requête SAP)
   - POST /api/quote_draft/{id}/line/{line_id}/retry (retry ligne isolée)
   - GET /api/quote_draft/{id}/logs (traçabilité complète)

**Fichiers modifiés :**

- `routes/routes_webhooks.py:136-236` - Refactorisé pour appeler mail_processor
- `main.py` - Enregistrement routes `/api/mail/*` et `/api/quote_draft/*`

**Base de données SQLite :**

**Table `quote_draft` :**
```sql
CREATE TABLE quote_draft (
    id TEXT PRIMARY KEY,                    -- UUID
    mail_id TEXT UNIQUE NOT NULL,           -- Idempotence
    client_code TEXT,                       -- CardCode SAP ou NULL
    client_status TEXT,                     -- FOUND | NOT_FOUND | AMBIGUOUS
    status TEXT DEFAULT 'ANALYZED',         -- ANALYZED | VALIDATED | SAP_CREATED
    raw_email_payload TEXT NOT NULL,        -- JSON complet email
    lines TEXT NOT NULL,                    -- JSON array avec métadonnées SAP
    created_at TEXT,
    updated_at TEXT
);
```

**Structure JSONB lines :**
```json
[
  {
    "line_id": "uuid-ligne-1",
    "supplier_code": "HST-117-03",
    "description": "SIZE 3 PUSHER BLADE",
    "quantity": 50,
    "sap_item_code": "C315-6305RS",
    "sap_status": "FOUND",
    "sap_price": 125.50,
    "search_metadata": {
        "search_type": "EXACT",
        "sap_query_used": "ItemCode search 'HST-117-03'",
        "search_timestamp": "2026-02-13T10:30:00Z",
        "match_score": 100
    }
  }
]
```

**Table `mail_processing_log` :**
```sql
CREATE TABLE mail_processing_log (
    id TEXT PRIMARY KEY,
    mail_id TEXT NOT NULL,
    step TEXT NOT NULL,
    status TEXT,                            -- SUCCESS | ERROR | PENDING
    details TEXT,
    timestamp TEXT
);
```

**Workflow complet :**

```
1. Email arrive → Webhook Microsoft 365
   ↓
2. POST /api/webhooks/notification
   ↓
3. auto_process_email(message_id) appelle mail_processor
   ↓
4. mail_processor.process_incoming_email():
   ├─ Log WEBHOOK_RECEIVED
   ├─ LLM Analysis (email_analyzer)
   ├─ Log LLM_ANALYSIS_COMPLETE
   ├─ SAP Client Search (sap_client)
   ├─ Log SAP_CLIENT_SEARCH_COMPLETE
   ├─ SAP Products Search (sap_client)
   ├─ Log SAP_PRODUCTS_SEARCH_COMPLETE
   ├─ Pricing (pricing_engine)
   ├─ Log PRICING_COMPLETE
   ├─ Build quote_draft structure
   ├─ quote_repo.create_quote_draft()
   └─ Log QUOTE_DRAFT_CREATED
   ↓
5. Dual-write email_analysis (backward compat)
   ↓
6. Utilisateur consulte → GET /api/quote_draft/{id}
   ↓ (< 50ms - lecture DB uniquement)
7. Affichage instantané (ZERO requête SAP)
```

**Garanties techniques :**

| Garantie | Implémentation |
|---|---|
| **Persistance stricte** | ✅ Toutes requêtes SAP effectuées UNE SEULE FOIS lors du traitement initial |
| **Idempotence** | ✅ UNIQUE constraint sur mail_id - double webhook safe |
| **Zero requête SAP au GET** | ✅ GET /api/quote_draft/{id} lecture DB uniquement (~50ms) |
| **Retry isolé** | ✅ POST /api/quote_draft/{id}/line/{line_id}/retry - Update ligne sans refaire workflow |
| **Logs complets** | ✅ 10+ étapes tracées dans mail_processing_log |
| **Backward compatible** | ✅ Dual-write email_analysis + quote_draft |

**Endpoints API :**

```
POST /api/mail/incoming                    # Traitement initial (idempotent)
GET  /api/quote_draft/{id}                 # Lecture seule (zero SAP)
POST /api/quote_draft/{id}/line/{line_id}/retry  # Retry ligne isolée
GET  /api/quote_draft/{id}/logs            # Logs traçabilité
```

**Bénéfices v2.7.0 :**

- ✅ **Persistance stricte** - ZERO requête SAP aux consultations
- ✅ **Idempotence garantie** - mail_id UNIQUE constraint
- ✅ **Performance optimale** - GET < 50ms (lecture DB uniquement)
- ✅ **Traçabilité exhaustive** - Logs structurés 10+ étapes
- ✅ **Retry granulaire** - Relance ligne isolée sans refaire workflow
- ✅ **Architecture propre** - 5 modules séparés (mail_processor, sap_client, quote_repository, retry_service, mail_processing_log_service)
- ✅ **Backward compatible** - Dual-write pour transition progressive

**Statistiques implémentation :**

- Total fichiers créés : 6 fichiers
- Total lignes ajoutées : ~1580 lignes
- Total tables SQLite : 2 tables (quote_draft, mail_processing_log)
- Total endpoints API : 4 nouveaux endpoints
- Durée implémentation : ~2 heures

**Test de vérification :**

```bash
# Test imports
python -c "from services.mail_processor import get_mail_processor; print('OK')"

# Vérifier tables créées
python -c "import sqlite3; conn = sqlite3.connect('email_analysis.db'); \
cursor = conn.cursor(); cursor.execute(\"SELECT name FROM sqlite_master WHERE type='table'\"); \
print([t[0] for t in cursor.fetchall()])"

# Résultat attendu: ['email_analysis', 'mail_processing_log', 'quote_draft']
```

#### 2.8 Visualisation Email Source + Stockage PJ + Corrections Manuelles ⭐ NOUVEAU (v2.8.0)

**Objectif :** Permettre à l'utilisateur de valider un devis en ayant accès à toutes les sources d'information : email original, pièces jointes, données extraites corrigibles — depuis une interface unifiée en onglets.

**Problématique résolue :**

Avant v2.8.0 :

- ❌ Corps de l'email affiché via `<iframe>` → bloqué par cookies/CORS en production
- ❌ Pièces jointes streamées depuis Graph API → ré-authentification à chaque visualisation
- ❌ Aucun moyen de corriger les données extraites par l'IA avant envoi SAP
- ❌ Interface QuoteSummary sans navigation structurée

**Solution v2.8.0 :**

Navigation par onglets et stockage local des pièces jointes.

**Architecture — 4 onglets dans QuoteSummary :**

```
┌────────────────────────────────────────────────────────────┐
│  QuoteSummary (React)                                       │
│  ┌──────────┬──────────────┬──────────────┬─────────────┐  │
│  │ Synthèse │ Email source │ Pièces jointes│ Données     │  │
│  │ (défaut) │              │   (N)         │ extraites   │  │
│  └──────────┴──────────────┴──────────────┴─────────────┘  │
│                                                              │
│  Synthèse : Client SAP + Articles + Pricing + Justification │
│  Email    : Métadonnées + Corps HTML (fetch + DOMPurify)    │
│  PJ       : Liste + Visualiseur (stockage local)            │
│  Données  : Tableau éditable avec corrections persistées    │
└────────────────────────────────────────────────────────────┘
```

**Onglet "Email source" — EmailSourceTab.tsx :**

- `fetch()` + `DOMPurify.sanitize()` remplace l'ancienne approche `<iframe>`
- Affiche métadonnées (expéditeur, sujet, date reçue) + corps HTML
- Fallback sur `bodyPreview` si le body ne charge pas
- Protection XSS : tags `script`, `iframe`, `form`, `input` filtrés

**Onglet "Pièces jointes" — AttachmentsTab.tsx :**

- Chargement depuis `GET /api/graph/emails/{id}/stored-attachments` (disque local)
- Si PJ non encore stockées : bouton "Télécharger maintenant" (`POST /store-attachments`)
- Visualiseur intégré : `<img>` pour images, `<iframe>` pour PDF (via `FileResponse` local)
- Téléchargement direct via `?download=true`
- Avantage : aucune ré-authentification Graph, fiabilité maximale

**Onglet "Données extraites" — ExtractedDataTab.tsx :**

| Champ | Valeur extraite | Action |
| ----- | --------------- | ------ |
| Client (nom) | MARMARA CAM | ✏️ Corriger |
| Client (code SAP) | C00042 | ✏️ Corriger |
| Produit 1 — Référence | C315-6305RS | ✏️ Corriger |
| Produit 1 — Quantité | 10 | ✏️ Corriger |
| Délai de livraison | Urgent | ✏️ Corriger |

- Édition inline (clic crayon → Input → Valider)
- Corrections persistées via `PUT /api/graph/emails/{id}/corrections`
- Badge "Corrigé" + affichage valeur originale barrée
- Annulation correction via `DELETE /corrections/{field_type}/{field_name}`
- **Corrections appliquées automatiquement** lors de l'envoi dans SAP (`apply_corrections()`)

**Backend — Nouveau service de stockage PJ :**

```python
class AttachmentStorageService:
    """
    Télécharge et stocke localement les PJ Office 365.
    Stockage : data/attachments/{sha256_email_id}/{att_id}_{filename}
    Limite : 15 MB par pièce jointe
    """
    async def download_and_store_all(email_id, message_id, graph_service)
    def get_stored_attachments(email_id) -> List[StoredAttachment]
    def get_attachment_path(email_id, attachment_id) -> Optional[Path]
    def cleanup_old_attachments(days=30)
```

Table SQLite `stored_attachments` dans `email_analysis.db` :
```sql
CREATE TABLE stored_attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id TEXT NOT NULL,
    attachment_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    content_type TEXT,
    size INTEGER,
    local_path TEXT NOT NULL,
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(email_id, attachment_id)
)
```

**Backend — Service corrections manuelles :**

```python
class QuoteCorrectionsDB:
    """
    Persistance des corrections sur les champs extraits.
    field_type : "client" | "product" | "delivery" | "general"
    Désérialisation automatique (int, float, bool, JSON, str)
    """
    def save_correction(email_id, field_type, field_name, corrected_value, ...)
    def get_corrections(email_id) -> List[QuoteCorrection]
    def apply_corrections(email_id, analysis_result) -> analysis_result  # deepcopy overlay
    def delete_correction(email_id, field_type, field_name, field_index)
```

Table SQLite `quote_corrections` dans `email_analysis.db` :
```sql
CREATE TABLE quote_corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id TEXT NOT NULL,
    field_type TEXT NOT NULL,       -- "client" | "product" | "delivery"
    field_index INTEGER,            -- Index produit (0-based) ou NULL
    field_name TEXT NOT NULL,
    original_value TEXT,
    corrected_value TEXT NOT NULL,
    corrected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    corrected_by TEXT DEFAULT 'user',
    UNIQUE(email_id, field_type, field_index, field_name)
)
```

**Nouveaux endpoints API (`routes/routes_graph.py`) :**

```
GET  /api/graph/emails/{id}/stored-attachments
     → Liste les PJ stockées localement

POST /api/graph/emails/{id}/store-attachments
     → Déclenche téléchargement/stockage (idempotent)

GET  /api/graph/emails/{id}/stored-attachments/{att_id}/serve
     → Sert le fichier depuis disque (FileResponse)
     → Paramètre ?download=true pour forcer téléchargement

GET  /api/graph/emails/{id}/corrections
     → Lit toutes les corrections manuelles

PUT  /api/graph/emails/{id}/corrections
     → Sauvegarde corrections (batch)
     Body: { corrections: [{field_type, field_name, field_index, corrected_value, original_value}] }

DELETE /api/graph/emails/{id}/corrections/{field_type}/{field_name}
     → Supprime une correction (avec ?field_index= optionnel)
```

**Déclenchement automatique stockage PJ :**

Lors de chaque analyse email (`POST /analyze`), si l'email a des pièces jointes, le téléchargement est lancé en arrière-plan (non-bloquant) :

```python
# Dans analyze_email_endpoint() — routes_graph.py
if email.has_attachments:
    asyncio.create_task(
        attachment_storage.download_and_store_all(message_id, message_id, graph_service)
    )
```

#### 2.9 Service SAP B1 Sales Quotation ⭐ NOUVEAU (v2.8.0)

**Objectif :** Service dédié à la création de devis SAP Business One (Sales Quotations) depuis les données NOVA, avec gestion robuste des erreurs et traçabilité complète.

**Fonctionnalités :**

- 📄 **Création Sales Quotation** via SAP B1 Service Layer (`POST /Quotations`)
- 🔐 **Authentification B1SESSION** avec retry automatique sur 401
- ⏱️ **Timeout configurable** (10 secondes par défaut)
- 📦 **Produits SAP ou hors-SAP** (ItemCode optionnel)
- 🔍 **Validation Pydantic** des données avant envoi
- 📝 **Payload audit** retourné pour traçabilité

**Modèles :**

```python
class QuotationLine(BaseModel):
    ItemCode: Optional[str]         # Optionnel (produit non-SAP supporté)
    ItemDescription: str            # Obligatoire
    Quantity: float                 # > 0
    UnitPrice: Optional[float]
    DiscountPercent: float = 0.0    # 0-100%
    TaxCode: Optional[str]
    WarehouseCode: Optional[str]
    FreeText: Optional[str]

class QuotationPayload(BaseModel):
    CardCode: str                   # Obligatoire
    DocumentLines: List[QuotationLine]  # Au moins 1 ligne
    DocDate: Optional[str]          # Format YYYY-MM-DD (date du jour si absent)
    DocDueDate: Optional[str]
    ValidUntil: Optional[str]
    Comments: Optional[str]
    SalesPersonCode: Optional[int]
    NumAtCard: Optional[str]
    # Champs NOVA (exclus du payload SAP) :
    email_id: Optional[str]
    email_subject: Optional[str]
    nova_source: str = "NOVA_MAIL_TO_BIZ"
```

**Endpoints :**

```
POST /api/sap/quotation
     → Crée un devis SAP
     → 201 : {doc_entry, doc_num, doc_total, card_name, sap_payload}
     → 503 : Timeout ou échec connexion SAP
     → 422 : Erreur métier SAP (CardCode inconnu, etc.)

GET  /api/sap/quotation/status
     → Health check connexion SAP
```

**Tests :**

```bash
pytest tests/test_sap_quotation.py -v
# 24 tests - 0 erreurs
# TestQuotationModels (5), TestBuildSapPayload (9), TestCreateSalesQuotation (5), TestSingleton (1)
```

**Fichiers créés :**

- `services/sap_quotation_service.py` - Service avec auth B1SESSION, retry 401, timeout 10s
- `routes/routes_sap_quotation.py` - Endpoints POST /api/sap/quotation
- `tests/test_sap_quotation.py` - 24 tests unitaires (mock HTTP)

**Bénéfices v2.8.0 :**

- ✅ **Visualisation complète** — email, PJ et données dans un seul écran
- ✅ **Fiabilité PJ** — stockage local, zéro dépendance Graph pour la consultation
- ✅ **Corrections traçables** — persistées en SQLite, appliquées automatiquement au payload SAP
- ✅ **Interface structurée** — 4 onglets dans QuoteSummary (shadcn/ui Tabs)
- ✅ **Sécurité HTML** — DOMPurify sur le corps email (protection XSS)
- ✅ **Quotation SAP robuste** — retry 401, timeout, validation Pydantic, 24 tests

**Fichiers créés/modifiés :**

| Fichier | Action | Lignes |
| ------- | ------ | ------ |
| `services/attachment_storage_service.py` | Créé | ~400 |
| `services/quote_corrections_db.py` | Créé | ~340 |
| `services/sap_quotation_service.py` | Créé | ~280 |
| `routes/routes_sap_quotation.py` | Créé | ~120 |
| `tests/test_sap_quotation.py` | Créé | ~362 |
| `mail-to-biz/src/components/EmailSourceTab.tsx` | Créé | ~150 |
| `mail-to-biz/src/components/AttachmentsTab.tsx` | Créé | ~180 |
| `mail-to-biz/src/components/ExtractedDataTab.tsx` | Créé | ~440 |
| `mail-to-biz/src/lib/graphApi.ts` | Modifié | +80 lignes |
| `mail-to-biz/src/components/QuoteSummary.tsx` | Modifié | restructuré Tabs |
| `routes/routes_graph.py` | Modifié | +5 endpoints |

---

### 3. Moteur de Pricing Intelligent RONDOT-SAS ⭐ NOUVEAU

**Objectif :** Calculer automatiquement les prix de vente selon l'organigramme décisionnel RONDOT-SAS (4 CAS déterministes).

**Fonctionnalités :**

- 🎯 **4 CAS de pricing automatiques** basés sur l'historique de vente
- 📊 **Analyse historiques SAP** (factures ventes + achats)
- 💰 **Calcul prix moyen pondéré** (récence + quantité)
- 🔍 **Détection variation prix fournisseur** (seuil 5%)
- ⚠️ **Alertes commerciales** pour variations importantes
- 📝 **Traçabilité exhaustive** de chaque décision
- 🗃️ **Audit trail SQLite** avec justifications complètes
- ✅ **Validation commerciale** pour cas critiques

#### Les 4 CAS de Pricing

| CAS             | Nom                              | Condition                                                             | Décision                          | Validation | Confiance |
| --------------- | -------------------------------- | --------------------------------------------------------------------- | ---------------------------------- | ---------- | --------- |
| **CAS 1** | HC (Historique Client)           | Article déjà vendu à CE client + prix fournisseur stable (< 5%)    | Reprendre prix dernière vente     | ❌ Non     | 1.0       |
| **CAS 2** | HCM (Historique Client Modifié) | Article déjà vendu à CE client + prix fournisseur modifié (≥ 5%) | Recalculer avec marge 45% + Alerte | ✅ Oui     | 0.9       |
| **CAS 3** | HA (Historique Autres)           | Article jamais vendu à CE client, mais vendu à AUTRES clients       | Prix moyen pondéré des ventes    | ❌ Non*    | 0.85      |
| **CAS 4** | NP (Nouveau Produit)             | Article jamais vendu nulle part                                       | Prix fournisseur + marge 45%       | ✅ Oui     | 0.7       |

*\*Validation requise si < 3 ventes de référence*

#### Architecture Pricing

**Fichiers créés :**

- `services/pricing_models.py` - Modèles Pydantic (PricingDecision, PricingContext)
- `services/pricing_engine.py` - Moteur de calcul CAS 1/2/3/4
- `services/sap_history_service.py` - Accès historiques SAP (/Invoices, /PurchaseInvoices)
- `services/pricing_audit_db.py` - Base audit SQLite avec statistiques
- `services/transport_calculator.py` - Calculateur coût transport (Phase 1 basique)

**Workflow Pricing :**

```
1. Récupérer prix fournisseur (supplier_tariffs_db)
   ↓
2. Recherche historique vente à CE client
   - OUI → Vérifier variation prix fournisseur
     - < 5% → CAS 1 : Reprendre prix
     - ≥ 5% → CAS 2 : Recalculer + Alerte
   - NON → Continuer
   ↓
3. Recherche ventes à AUTRES clients
   - OUI → CAS 3 : Prix moyen pondéré
   - NON → Continuer
   ↓
4. Aucun historique
   → CAS 4 : Prix fournisseur + marge 45% + Validation
```

**Exemple de Décision :**

```json
{
  "decision_id": "uuid-123",
  "case_type": "CAS_2_HCM",
  "calculated_price": 174.00,
  "supplier_price": 120.00,
  "margin_applied": 45.0,
  "justification": "Prix recalculé (174.00 EUR) avec marge 45%. Ancien prix vente : 150.00 EUR. Écart : +24.00 EUR (+16.00%). Variation prix fournisseur : +14.00% (instable).",
  "requires_validation": true,
  "validation_reason": "Variation prix fournisseur importante (+14.00%)",
  "alerts": [
    "⚠ ALERTE COMMERCIALE : Variation prix fournisseur +14.00%",
    "Impact prix vente : +24.00 EUR"
  ],
  "confidence_score": 0.9,
  "last_sale_date": "2025-11-15",
  "last_sale_price": 150.00,
  "last_sale_doc_num": 12345
}
```

**Routes API :**

```
POST /api/pricing/calculate              # Calcul pricing intelligent
GET  /api/pricing/decisions              # Historique décisions
GET  /api/pricing/decisions/pending      # Décisions en attente validation
GET  /api/pricing/statistics             # Statistiques par CAS
```

**Base de Données Audit :**

- Table `pricing_decisions` - Toutes les décisions avec justifications
- Table `pricing_statistics` - Statistiques quotidiennes (répartition CAS, marges moyennes)
- Index sur `item_code`, `card_code`, `case_type`, `requires_validation`

**Intégration Mail-to-Biz :**

- Le moteur de pricing est automatiquement appelé lors de la création de devis depuis email
- Remplace le calcul basique de prix par un calcul intelligent contextualisé
- Toutes les décisions sont tracées dans la base d'audit

---

### 4. Quote Management - Synchronisation SAP ↔ Salesforce

**Objectif :** Vue unifiée et synchronisation des devis entre SAP et Salesforce.

**Fonctionnalités :**

- 📊 Vue unifiée SAP + Salesforce
- 🔍 Détection des incohérences
- 🗑️ Suppression en masse
- 📈 Statistiques temps réel
- 🎨 Interface web dédiée

**Statuts :**

- 🟢 **Synchronisé** : Cohérent dans les 2 systèmes
- 🟠 **SAP uniquement**
- 🔵 **Salesforce uniquement**
- 🔴 **Avec différences**

**Routes :**

```
GET  /api/quote-management/quotes      # Liste devis
POST /api/quote-management/quotes/delete  # Suppression
GET  /api/quote-management/quotes/stats   # Statistiques
GET  /quote-management                 # Interface web
```

**Fichiers :**

- `quote_management/quote_manager.py` - Logique métier
- `quote_management/api_routes.py` - Routes FastAPI
- `quote_management/quote_management_interface.html` - Interface

---

### 4. MCP Connectors - Protocole de Contexte Modèle

**Objectif :** Connecteurs MCP standardisés pour SAP et Salesforce.

**Salesforce MCP (`salesforce_mcp.py`) :**

- Outils MCP exposés :
  - `salesforce_query` - Requêtes SOQL
  - `salesforce_create_record` - Création enregistrements
  - `salesforce_update_record` - Mise à jour
  - `salesforce_delete_record` - Suppression
  - `salesforce_get_account_by_name` - Recherche comptes
  - `salesforce_create_opportunity` - Création opportunités

**SAP MCP (`sap_mcp.py`) :**

- Outils MCP exposés :
  - `sap_search_products` - Recherche produits
  - `sap_get_product_price` - Prix produits
  - `sap_create_quotation` - Création devis
  - `sap_get_quotation` - Récupération devis
  - `sap_search_customers` - Recherche clients

**Service MCP Connector (`services/mcp_connector.py`) :**

- Orchestration centralisée des appels MCP
- Cache Redis pour performance
- Gestion erreurs et reconnexions
- Support progression temps réel

---

### 5. Client Management - Validation et Enrichissement

**Services :**

#### Client Validator (`services/client_validator.py`)

Validation multi-sources des informations client :

- ✅ Validation SIRET via API INSEE
- ✅ Validation adresse via API Adresse Gouv
- ✅ Enrichissement via API Pappers
- ✅ Détection doublons intelligente

#### Company Search Service (`services/company_search_service.py`)

Recherche d'entreprises :

- 🔍 API INSEE (Sirene)
- 🔍 API Pappers
- 💾 Cache local PostgreSQL

#### Suggestion Engine (`services/suggestion_engine.py`)

Suggestions intelligentes avec IA + Fuzzy Matching :

- 🎯 Correspondance floue (SequenceMatcher)
- 🤖 Analyse LLM pour suggestions contextuelles
- 📊 Score de confiance

**Routes :**

```
POST /suggestions/client               # Suggestions clients
POST /api/clients/validate             # Validation client
GET  /api/clients/list                 # Liste clients SAP+SF
POST /api/company-search/search        # Recherche entreprises
```

---

### 6. Product Search - Recherche Multi-Sources

**Local Product Search (`services/local_product_search.py`) :**

- Base PostgreSQL avec pg_trgm (trigram similarity)
- Recherche floue ultra-rapide
- Synchronisation SAP → PostgreSQL
- Indexation automatique

**Product Search Engine (`services/product_search_engine.py`) :**

- Recherche hybride : Local + SAP direct
- Fallback intelligent
- Cache des résultats

**SAP Product Utils (`utils/sap_product_utils.py`) :**

- Utilitaires recherche SAP OData
- Parsing réponses SAP
- Gestion filtres complexes

**Routes :**

```
POST /api/products/search              # Recherche produits
GET  /api/products/{code}              # Détails produit
POST /api/products/sync                # Sync SAP → PostgreSQL
```

---

### 7. Supplier Tariffs - Base Tarifs Fournisseurs

**Objectif :** Indexation et recherche rapide dans les tarifs fournisseurs (Excel/PDF).

**Fonctionnalités :**

- 📁 Indexation automatique fichiers Excel/PDF
- 🔍 Recherche fulltext (SQLite FTS5)
- 💰 Extraction références + prix + désignations
- ⚡ Performance optimale avec cache

**Service (`services/supplier_tariffs_db.py`) :**

- SQLite avec FTS5 (Full-Text Search)
- Table : `supplier_products` (reference, designation, unit_price)
- Parsers : PyMuPDF (PDF) + OpenPyXL (Excel)

**Routes :**

```
POST /api/supplier-tariffs/index       # Lance indexation
GET  /api/supplier-tariffs/search      # Recherche produit
GET  /api/supplier-tariffs/stats       # Statistiques
```

**Configuration :**

```env
SUPPLIER_TARIFF_FOLDER=C:\Users\PPZ\RONDOT
```

---

## 🔧 Services Backend Clés

### Core Services

| Service                        | Fichier                               | Description                                                   |
| ------------------------------ | ------------------------------------- | ------------------------------------------------------------- |
| **LLM Extractor**        | `services/llm_extractor.py`         | Service IA générique (Claude/OpenAI) avec fallback          |
| **Email Analyzer**       | `services/email_analyzer.py`        | Analyse IA spécialisée emails (classification + extraction) |
| **Graph Service**        | `services/graph_service.py`         | Microsoft Graph API (OAuth2 + Token caching)                  |
| **SAP Business**         | `services/sap_business_service.py`  | SAP B1 Service Layer (Items, Partners, Quotations)            |
| **SAP**                  | `services/sap.py`                   | SAP B1 API basique                                            |
| **SAP Quote**            | `services/sap_quote_service.py`     | Service spécialisé récupération devis SAP                 |
| **Salesforce**           | `services/salesforce.py`            | Salesforce REST API (simple-salesforce)                       |
| **Price Engine**         | `services/price_engine.py`          | Calcul prix clients SAP                                       |
| **Pricing Engine**       | `services/pricing_engine.py`        | Moteur pricing intelligent RONDOT-SAS (CAS 1/2/3/4)           |
| **SAP History**          | `services/sap_history_service.py`   | Accès historiques SAP (factures ventes/achats)               |
| **Transport Calculator** | `services/transport_calculator.py`  | Calcul coûts transport (Phase 1 basique)                     |
| **Pricing Audit DB**     | `services/pricing_audit_db.py`      | Base audit décisions pricing SQLite                          |
| **Quote Validator**      | `services/quote_validator.py`       | Validation commerciale workflow (CAS 2 & 4)                   |
| **Dashboard Service**    | `services/dashboard_service.py`     | Métriques temps réel pricing & validation                   |
| **Currency Service**     | `services/currency_service.py`      | Taux de change multi-devises (EUR, USD, GBP, CHF)             |
| **Supplier Discounts**   | `services/supplier_discounts_db.py` | Remises fournisseurs (PERCENTAGE, FIXED_AMOUNT)               |
| **File Parsers**         | `services/file_parsers.py`          | Parsers PDF/Excel (PyMuPDF, OpenPyXL)                         |

### Workflow Services

| Service                       | Fichier                                  | Description                                            |
| ----------------------------- | ---------------------------------------- | ------------------------------------------------------ |
| **Devis Workflow**      | `workflow/devis_workflow.py`           | Orchestration complète génération devis (8 étapes) |
| **Client Creation**     | `workflow/client_creation_workflow.py` | Workflow création client multi-systèmes              |
| **Validation Workflow** | `workflow/validation_workflow.py`      | Validateur séquentiel multi-sources                   |

### Support Services

| Service                     | Fichier                           | Description                             |
| --------------------------- | --------------------------------- | --------------------------------------- |
| **Progress Tracker**  | `services/progress_tracker.py`  | Suivi progression workflows temps réel |
| **WebSocket Manager** | `services/websocket_manager.py` | Gestion connexions WebSocket multiples  |
| **Cache Manager**     | `services/cache_manager.py`     | Cache Redis pour référentiels         |
| **Health Checker**    | `services/health_checker.py`    | Tests santé au démarrage              |
| **Module Loader**     | `services/module_loader.py`     | Chargement dynamique modules            |

---

## 🛣️ Routes API Complètes

### Assistant Intelligent

```
GET  /api/assistant/interface          # Interface conversationnelle
POST /api/assistant/chat               # Chat NOVA
POST /api/assistant/workflow/create_quote  # Workflow complet
GET  /api/assistant/prompt             # Prompt système
WS   /ws/assistant/{task_id}           # WebSocket progression
```

### Clients

```
GET  /api/clients/list                 # Liste clients (SAP + SF)
POST /api/clients/validate             # Validation client
POST /suggestions/client               # Suggestions clients
POST /api/company-search/search        # Recherche entreprises INSEE/Pappers
```

### Produits

```
POST /api/products/search              # Recherche produits
GET  /api/products/{code}              # Détails produit
POST /api/products/sync                # Sync SAP → PostgreSQL
```

### Devis

```
POST /api/devis/create                 # Création devis
GET  /api/devis/{doc_entry}            # Détails devis
GET  /api/quote-details/{id}           # Détails complets devis
```

### Microsoft Graph (Mail-to-Biz)

```
GET  /api/graph/test-connection        # Test connexion
GET  /api/graph/emails                 # Liste emails
GET  /api/graph/emails/{id}            # Email complet
POST /api/graph/emails/{id}/analyze    # Analyse IA
GET  /api/graph/emails/{id}/attachments  # Pièces jointes
```

### SAP Business (Mail-to-Biz)

```
GET  /api/sap/health                   # Connexion SAP
POST /api/sap/items/search             # Recherche articles
POST /api/sap/items/price              # Prix article
POST /api/sap/partners/search          # Recherche client
POST /api/sap/partners/create          # Création client
POST /api/sap/quotations/create        # Création devis
POST /api/sap/quotations/from-email    # Devis depuis email (orchestration)
```

### Pricing Intelligent (RONDOT-SAS) ⭐ NOUVEAU

```
POST /api/pricing/calculate            # Calcul pricing intelligent
GET  /api/pricing/decisions            # Historique décisions
GET  /api/pricing/decisions/pending    # Décisions en attente validation
POST /api/pricing/decisions/{id}/validate  # Valider décision
GET  /api/pricing/statistics           # Statistiques par CAS
GET  /api/pricing/history/{item_code}  # Historique prix article
```

### Validation Commerciale (Phase 4) ⭐ NOUVEAU

```
GET  /api/validations/pending          # Liste validations en attente
GET  /api/validations/{id}             # Détails validation
POST /api/validations/{id}/approve     # Approuver validation
POST /api/validations/{id}/reject      # Rejeter validation
POST /api/validations/bulk-approve     # Approbation en masse
GET  /api/validations/statistics/summary  # Statistiques validation
GET  /api/validations/dashboard/summary   # Dashboard complet
GET  /api/validations/urgent/count     # Compteur urgents
GET  /api/validations/by-priority/{priority}  # Par priorité
GET  /api/validations/by-case-type/{case_type}  # Par CAS
POST /api/validations/expire-old       # Expirer anciennes
```

### Tarifs Fournisseurs

```
POST /api/supplier-tariffs/index       # Indexation
GET  /api/supplier-tariffs/search      # Recherche
GET  /api/supplier-tariffs/stats       # Statistiques
```

### Validation Produits (Apprentissage Automatique) ⭐ NOUVEAU (v2.5.0)

```
GET  /api/products/pending              # Liste produits en attente validation
POST /api/products/validate             # Associer code externe à ItemCode SAP
POST /api/products/create               # Créer nouveau produit dans SAP
POST /api/products/bulk-create          # Création en masse depuis PENDING
GET  /api/products/mapping/statistics   # Statistiques apprentissage (total, validés, pending)
DELETE /api/products/mapping/{external_code}  # Supprimer mapping (avec supplier_card_code param)
GET  /api/products/search               # Recherche produits SAP pour modal association
```

### Quote Management

```
GET  /api/quote-management/quotes      # Liste devis
POST /api/quote-management/quotes/delete  # Suppression
GET  /api/quote-management/quotes/stats   # Statistiques
```

### Système

```
GET  /health                           # Santé système
GET  /diagnostic/connections           # Diagnostic connexions
GET  /diagnostic/data-retrieval        # Diagnostic données
POST /diagnostic/recheck               # Nouvelle vérification
GET  /docs                             # Documentation Swagger
```

### Interfaces Web

```
GET  /interface/itspirit               # NOVA Assistant
GET  /mail-to-biz                      # Mail-to-Biz React SPA
GET  /quote-management                 # Quote Management
GET  /edit-quote/{quote_id}            # Édition devis
```

---

## ⚙️ Configuration

### Variables d'Environnement Principales

#### Général

```env
NOVA_MODE=production
APP_HOST=0.0.0.0
APP_PORT=8000
LOG_LEVEL=info
```

#### Intelligence Artificielle

```env
ANTHROPIC_API_KEY=sk-ant-api03-***
ANTHROPIC_MODEL=claude-3-7-sonnet-20250219
OPENAI_API_KEY=sk-proj-***
OPENAI_MODEL=gpt-4o
```

#### SAP Business One

```env
SAP_REST_BASE_URL=https://141.94.132.62:50000/b1s/v1
SAP_USER=manager
SAP_CLIENT=SBODemoFR
SAP_CLIENT_PASSWORD=***

# Configuration SAP RONDOT
SAP_USER_RONDOT=manager
SAP_CLIENT_RONDOT=RON_20260109
SAP_CLIENT_PASSWORD_RONDOT=***
```

#### Salesforce

```env
SALESFORCE_USERNAME=***@agentforce.com
SALESFORCE_PASSWORD=***
SALESFORCE_SECURITY_TOKEN=***
SALESFORCE_DOMAIN=orgfarm-***-dev-ed.develop.my.salesforce.com
SALESFORCE_URL=https://orgfarm-***-dev-ed.develop.my.salesforce.com
SALESFORCE_Cleconsommateur=***
SALESFORCE_Secretconsommateur=***
```

#### Microsoft Graph (Office 365)

```env
MS_TENANT_ID=203feedd-7ba1-4180-a7c4-bb0d4e1d238f
MS_CLIENT_ID=717c52b2-bb6d-4028-9f38-44a33b3d333c
MS_CLIENT_SECRET=***
MS_MAILBOX_ADDRESS=devis@rondot-poc.itspirit.ovh
```

#### Base de Données

```env
DATABASE_URL=postgresql://nova_user:***@localhost:5432/nova_mcp
REDIS_URL=redis://localhost:6379/0
```

#### APIs Validation Client

```env
# INSEE (Sirene)
INSEE_API_KEY=***
INSEE_CONSUMER_KEY=***
INSEE_CONSUMER_SECRET=Search_Societe

# Pappers (Enrichissement)
PAPPERS_API_KEY=***
PAPPERS_URL=https://api.pappers.fr/v2/
```

#### Tarifs Fournisseurs

```env
SUPPLIER_TARIFF_FOLDER=C:\Users\PPZ\RONDOT
```

#### Pricing Engine (RONDOT-SAS) ⭐ NOUVEAU

```env
PRICING_ENGINE_ENABLED=true
PRICING_DEFAULT_MARGIN=45.0
PRICING_STABILITY_THRESHOLD=5.0
PRICING_LOOKBACK_DAYS=365
PRICING_MIN_REFERENCE_SALES=3
PRICING_REQUIRE_VALIDATION_CAS_2=true
PRICING_REQUIRE_VALIDATION_CAS_4=true
PRICING_BASE_CURRENCY=EUR
```

#### Workflow Validation (Phase 4) ⭐ NOUVEAU

```env
PRICING_CREATE_VALIDATIONS=true
VALIDATION_AUTO_APPROVE_THRESHOLD=3.0
VALIDATION_AUTO_REJECT_THRESHOLD=50.0
VALIDATION_EXPIRATION_HOURS=48
VALIDATION_URGENT_EXPIRATION_HOURS=4
VALIDATION_NOTIFY_ON_CREATION=true
VALIDATION_EMAIL=validation@rondot-sas.fr
VALIDATION_HIGH_PRIORITY_THRESHOLD=10.0
VALIDATION_URGENT_PRIORITY_THRESHOLD=20.0
CURRENCY_CACHE_HOURS=4
```

#### WebSocket et Validation

```env
WEBSOCKET_ENABLED=true
WEBSOCKET_TIMEOUT=300
USER_VALIDATION_ENABLED=true
AUTO_SUGGEST_THRESHOLD=0.8
MAX_ALTERNATIVES=5
```

---

## 📥 Installation et Démarrage

### Prérequis

- **OS :** Windows Server 2019+ ou Linux
- **Python :** 3.10+
- **Node.js :** 18+ (pour Mail-to-Biz frontend)
- **PostgreSQL :** 13+ avec extension pg_trgm
- **Redis :** 6+ (optionnel, pour cache)
- **SAP Business One :** Service Layer activé
- **Salesforce :** Org avec API access

### Installation Backend

```bash
# Cloner le projet
cd C:\Users\PPZ\NOVA-SERVER

# Créer environnement virtuel
python -m venv .venv
.venv\Scripts\activate

# Installer dépendances
pip install -r requirements.txt

# Configurer .env
cp .env.example .env
# Éditer .env avec vos credentials

# Initialiser base de données
alembic upgrade head

# Installer extension PostgreSQL
python install_pg_trgm.py

# Indexer tarifs fournisseurs
python -c "from services.supplier_tariffs_db import index_tariffs; index_tariffs()"
```

### Installation Frontend (Mail-to-Biz)

```bash
cd mail-to-biz
npm install
npm run build

# Les fichiers buildés seront dans frontend/
```

### Démarrage

```bash
# Méthode 1 : Script PowerShell (Windows)
.\start_nova.ps1

# Méthode 2 : Uvicorn direct
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Méthode 3 : Production (sans reload)
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Vérification

```bash
# Health check
curl http://localhost:8001/health

# Interface NOVA
http://localhost:8001/interface/itspirit

# Interface Mail-to-Biz
http://localhost:8001/mail-to-biz

# Documentation API
http://localhost:8001/docs
```

---

## 🧪 Tests

### Tests Unitaires

```bash
pytest tests/
pytest tests/ -v                    # Verbose
pytest tests/ -m integration        # Tests d'intégration seulement
pytest tests/test_workflow_demo.py  # Test workflow complet
```

### Tests Manuels

```bash
# Test connexion SAP
python diagnostic_sap_products.py

# Test connexion Salesforce
python tests/test_integration_workflow.py

# Test MCP
python scripts/debug_mcp_responses.py

# Test client listing
python scripts/test_client_listing.py
```

### Tests API

```bash
# Chat NOVA
curl -X POST http://localhost:8001/api/assistant/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Créer un devis pour 10 réf A00025 pour Edge Communications"}'

# Recherche produit
curl -X POST http://localhost:8001/api/products/search \
  -H "Content-Type: application/json" \
  -d '{"query": "imprimante", "limit": 5}'

# Validation client
curl -X POST http://localhost:8001/api/clients/validate \
  -H "Content-Type: application/json" \
  -d '{"siret": "12345678901234", "nom": "Test SA"}'
```

---

## 🚀 Déploiement Production

### Windows Server (OVH)

**Configuration actuelle :**

- Serveur : Windows Server 2019
- IP : 178.33.233.120
- Répertoire : `C:\Users\PPZ\NOVA-SERVER`

**Service Windows (NSSM) :**

```powershell
# Installer NSSM
choco install nssm

# Créer service
nssm install NOVA "C:\Users\PPZ\NOVA-SERVER\.venv\Scripts\python.exe" "C:\Users\PPZ\NOVA-SERVER\.venv\Scripts\uvicorn.exe main:app --host 0.0.0.0 --port 8000"

# Configurer
nssm set NOVA AppDirectory "C:\Users\PPZ\NOVA-SERVER"
nssm set NOVA AppStdout "C:\Users\PPZ\NOVA-SERVER\logs\nova.log"
nssm set NOVA AppStderr "C:\Users\PPZ\NOVA-SERVER\logs\nova_error.log"

# Démarrer
nssm start NOVA
```

**Pare-feu :**

```powershell
# Autoriser port 8000
New-NetFirewallRule -DisplayName "NOVA Server" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

### Linux / Docker (Optionnel)

```dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t nova-server .
docker run -d -p 8000:8000 --env-file .env --name nova nova-server
```

---

## 🎉 Nouveautés Version 2.6.0 (13/02/2026)

### Webhook Microsoft Graph - Traitement Automatique 100% ⭐ MAJEUR

Transformation complète du workflow Mail-to-Biz avec traitement automatique en background des emails dès leur réception.

**Problème résolu :**

- ❌ Avant : Retraitement systématique des emails à chaque visite
- ❌ Avant : Chargement inbox très lent (20-50 secondes)
- ❌ Avant : 3 clics manuels requis par devis

**Solution v2.6.0 :**

- ✅ Traitement automatique background via webhook Microsoft Graph
- ✅ Persistance SQLite (email_analysis.db)
- ✅ Chargement inbox instantané (< 1 seconde)
- ✅ Affichage synthèse instantané (< 50ms)
- ✅ Zéro clic manuel requis

**Gains mesurés :**

| Métrique | Avant | Après | Gain |
|----------|-------|-------|------|
| Chargement inbox | 20-50s | < 1s | **-95%** |
| Affichage synthèse | 2-5s | < 50ms | **-99%** |
| Actions manuelles | 3 clics | 0 clic | **100% auto** |

**Fichiers créés** (~1200 lignes) :

- `services/webhook_service.py` (319 lignes) - Gestion subscriptions
- `routes/routes_webhooks.py` (386 lignes) - Endpoint webhook
- `services/email_analysis_db.py` (220 lignes) - Persistance
- Scripts : `register_webhook.py`, `renew_webhook.py`, `get_user_id.py`
- Docs : `WEBHOOK_CONFIGURATION_GUIDE.md`, `INSTRUCTIONS_WEBHOOK.txt`

**Architecture :**

```
Email arrive → Webhook notifie NOVA (< 30s)
           → Traitement auto background (2-5s)
           → Sauvegarde DB (< 50ms)
           → User se connecte → Synthèse déjà prête
```

**Configuration requise :**

```env
WEBHOOK_NOTIFICATION_URL=https://nova-rondot.itspirit.ovh/api/webhooks/notification
WEBHOOK_CLIENT_STATE=secret_token
GRAPH_USER_ID=user-id
```

**Renouvellement automatique :**

Webhook expire après 3 jours. Planifier tâche Windows :
- Programme : `python renew_webhook.py`
- Fréquence : Quotidienne à 09:00

**Voir section 2.6** du README pour documentation complète.

---

## 📊 Monitoring et Logs

### Logs

```
logs/
├── nova.log                  # Log principal
├── workflow_devis.log        # Logs workflows
├── company_search.log        # Logs recherche entreprises
└── nova_error.log            # Erreurs critiques
```

### Health Checks

```bash
# Santé globale
curl http://localhost:8001/health

# Connexions détaillées
curl http://localhost:8001/diagnostic/connections

# Récupération données
curl http://localhost:8001/diagnostic/data-retrieval

# Forcer nouvelle vérification
curl -X POST http://localhost:8001/diagnostic/recheck
```

---

## 📈 Performance

### Métriques Actuelles

- **Temps génération devis** : < 2 minutes (avec validation complète)
- **Taux succès** : > 95%
- **Disponibilité** : 99.9%
- **Précision validation client** : > 98%
- **Recherche produits locale** : < 100ms (PostgreSQL trigram)

### Optimisations Implémentées

- ✅ Cache Redis pour référentiels (clients, produits)
- ✅ PostgreSQL avec pg_trgm pour recherche floue rapide
- ✅ SQLite FTS5 pour tarifs fournisseurs
- ✅ Token caching Microsoft Graph (20 min)
- ✅ Session caching SAP (20 min)
- ✅ Lazy loading emails (pagination)
- ✅ React.memo pour optimisation UI

---

## 🗺️ Roadmap

### ✅ Phase 1 - POC (Terminée)

- [X] Assistant NOVA opérationnel
- [X] Intégrations SAP/Salesforce/Claude
- [X] Interface publique
- [X] Validation client multi-sources

### ✅ Phase 2 - Mail-to-Biz (Terminée - Fév 2026)

- [X] Intégration Microsoft Graph
- [X] Analyse IA emails
- [X] Création automatique devis SAP
- [X] Base tarifs fournisseurs
- [X] Interface React moderne

### ✅ Phase 3 - Pricing Intelligent RONDOT-SAS (Terminée - Fév 2026)

- [X] Moteur pricing 4 CAS (HC, HCM, HA, NP)
- [X] Accès historiques SAP (/Invoices, /PurchaseInvoices)
- [X] Calcul prix moyen pondéré (récence + quantité)
- [X] Détection variation prix fournisseur (seuil 5%)
- [X] Alertes commerciales automatiques
- [X] Base audit SQLite (pricing_decisions)
- [X] Traçabilité exhaustive des décisions
- [X] Calculateur transport basique
- [X] Intégration dans Mail-to-Biz

### ✅ Phase 4 - Enrichissement & Validation (Terminée - Fév 2026)

- [X] Workflow validation commerciale (CAS 2 & 4)
- [X] Dashboard pricing avec métriques temps réel
- [X] Service taux de change (API externe)
- [X] Gestion remises fournisseurs
- [X] Modèles validation completsValidationRequest/Decision/Result)
- [X] Priorités automatiques (URGENT/HIGH/MEDIUM/LOW)
- [X] Expirations automatiques (4h/48h)
- [X] Statistiques et métriques détaillées

### ✅ Phase 5 - Apprentissage Automatique Produits (Terminée - Fév 2026)

- [X] Système apprentissage codes produits externes (4 niveaux cascade)
- [X] Base de données mappings SQLite (product_code_mapping)
- [X] Dashboard React validation produits
- [X] Service création produits SAP (sap_product_creator.py)
- [X] Routes API validation (8 endpoints)
- [X] Extraction améliorée codes (4 patterns regex)
- [X] Matching intelligent avec fuzzy (seuil 90%)
- [X] Blacklist anti-faux positifs
- [X] Cache local SQLite (23,571 produits SAP)
- [X] Statistiques temps réel apprentissage

### 📋 Phase 6 - Production Avancée (En cours)

- [ ] Transport optimisé (API DHL, UPS, Chronopost, Geodis)
- [ ] Comparaison transporteurs en temps réel
- [ ] HTTPS + Authentification utilisateurs
- [ ] Application mobile React Native
- [ ] Machine Learning pricing avancé
- [ ] Export PDF devis automatique
- [ ] Envoi automatique emails clients
- [ ] Webhooks temps réel (notifications)
- [ ] Support multidevise étendu (JPY, CNY)
- [ ] Gestion remises clients SAP hiérarchiques
- [ ] Workflow approbation multi-niveaux
- [ ] Analytics avancés (BI dashboard)

---

## 🔐 Sécurité

### Mesures Actuelles

- ✅ Pare-feu Windows configuré (port 8000)
- ✅ API Keys sécurisées (.env gitignored)
- ✅ Authentification SAP/Salesforce/Graph
- ✅ Tokens OAuth2 en mémoire uniquement
- ✅ Validation SIRET/adresses via APIs officielles

### À Implémenter

- [ ] HTTPS avec certificat SSL
- [ ] Authentification utilisateurs (JWT)
- [ ] Rate limiting API
- [ ] Audit logs des actions critiques
- [ ] Chiffrement base de données sensibles

---

## 👥 Équipe

- **Philippe PEREZ** - Architecte IA / Chef de projet (2j/semaine)
- **Bruno CHARNAL** - Support technique (0.5j/semaine)

---

## 📚 Documentation Complémentaire

- **Guide Utilisateur** : `MANUEL_UTILISATEUR.md`
- **Guide Technique** : `GUIDE_TECHNIQUE_COMPLET.md`
- **Scénarios Test** : `SCENARIOS_DEMONSTRATION.md`
- **Mail-to-Biz** : `mail-to-biz/README.md`
- **Quote Management** : `quote_management/README.md`
- **Pricing Intelligent Phase 1** : `IMPLEMENTATION_PHASE1_COMPLETE.md`
- **Apprentissage Automatique Produits** : Voir section 2.4 (ci-dessus) ⭐ NOUVEAU (v2.5.0)

---

## 🆘 Support et Dépannage

### Problèmes Courants

**Interface inaccessible**

```bash
# Vérifier health
curl http://localhost:8001/health

# Vérifier logs
tail -f logs/nova.log

# Redémarrer
.\start_nova.ps1
```

**Erreur connexion SAP**

```bash
# Test direct
python diagnostic_sap_products.py

# Vérifier credentials .env
echo $SAP_REST_BASE_URL
```

**Erreur PostgreSQL**

```bash
# Vérifier service
pg_ctl status

# Tester connexion
psql -U nova_user -d nova_mcp

# Installer pg_trgm
python install_pg_trgm.py
```

**Emails non récupérés (Mail-to-Biz)**

```bash
# Test connexion Graph
curl http://localhost:8001/api/graph/test-connection

# Vérifier token
# Les tokens expirent après 1h - redémarrer le serveur
```

---

## 📞 Contact

**Email** : support@itspirit.ovh

**Documentation API** : http://178.33.233.120:8000/docs

**Interface NOVA** : http://178.33.233.120:8000/interface/itspirit

---

## 📄 Licence

Propriétaire - ITSpirit © 2025-2026

---

**🌟 NOVA-SERVER est opérationnel et accessible publiquement !**

**Version** : 2.6.0
**Build** : 2026-02-13
**Python** : 3.10+
**FastAPI** : 0.104+
**React** : 18+

---

## 🎉 Nouveautés Version 2.5.0 (10/02/2026)

### Apprentissage Automatique & Validation Produits ⭐ MAJEUR

Système intelligent d'apprentissage automatique pour codes produits externes (fournisseurs) avec validation et création dans SAP B1.

**Problématique résolue :** Les emails contiennent des références fournisseurs (ex: "HST-117-03", "TRI-037") qui n'existent pas dans SAP. Le système désormais :
- ✅ Détecte automatiquement les codes inconnus
- ✅ Les matche intelligemment (cascade 4 niveaux)
- ✅ Apprend les associations validées
- ✅ Permet la création de nouveaux produits SAP

**Architecture :**

```
Email → Extraction (4 regex) → Cascade 4 niveaux
                                 ├─ Exact Match (100) ✅
                                 ├─ Learned (95) ✅
                                 ├─ Fuzzy (≥90) ✅
                                 └─ PENDING → Dashboard React
                                               ├─ [Associer] existant
                                               ├─ [Créer] dans SAP
                                               └─ [Rejeter]
```

**Fichiers créés** (v2.5.0 - ~1550 lignes) :

- `services/product_mapping_db.py` (300 lignes) - Base apprentissage SQLite
- `services/sap_product_creator.py` (300 lignes) - Création produits SAP B1
- `routes/routes_product_validation.py` (450 lignes) - 8 endpoints API
- `mail-to-biz/src/pages/ProductValidation.tsx` (500 lignes) - Dashboard React

**Fichiers modifiés** :

- `services/email_matcher.py` - Cascade intelligente 4 niveaux (~600 lignes)
- `mail-to-biz/src/App.tsx` - Route `/products/validation`
- `main.py` - Enregistrement routes validation

**Nouveaux Endpoints API :**

```
GET  /api/products/pending              # Liste produits en attente
POST /api/products/validate             # Associer code externe → SAP
POST /api/products/create               # Créer produit dans SAP
POST /api/products/bulk-create          # Création en masse
GET  /api/products/mapping/statistics   # Statistiques apprentissage
DELETE /api/products/mapping/{code}     # Supprimer mapping
GET  /api/products/search               # Recherche produits SAP
```

**Dashboard React :**

- URL : `http://localhost:8001/mail-to-biz/products/validation`
- Statistiques temps réel (En attente / Validés / Total)
- Actions : [Associer] [Créer] [Rejeter]
- Recherche live dans 23,571 produits SAP
- Formulaire création produit SAP complet

**Bénéfices :**

- ✅ **Apprentissage progressif** - Chaque validation enrichit la base
- ✅ **Zéro duplication** - Codes fournisseurs uniques
- ✅ **Traçabilité complète** - Historique toutes associations
- ✅ **Création SAP intégrée** - Pas de double saisie
- ✅ **Performance** - Cache local SQLite
- ✅ **Scalabilité** - Milliers de codes fournisseurs supportés

**Exemple réel :** PDF Marmara Cam (28 produits SHEPPEE)
- 1ère analyse → 35 codes PENDING
- Validation manuelle → 32 validés, 3 rejetés
- 2ème email SHEPPEE → 32 codes auto-reconnus (Score 95) ✅

**Test du système :**

```bash
# 1. Rebuild frontend
cd mail-to-biz && npm run build

# 2. Redémarrer backend
python main.py

# 3. Accéder dashboard
http://localhost:8001/mail-to-biz/products/validation
```

---

## 🎉 Nouveautés Version 2.3.0 (07/02/2026)

### Phase 3 : Moteur de Pricing Intelligent RONDOT-SAS

Implémentation complète de l'organigramme décisionnel RONDOT-SAS avec 4 CAS de pricing automatiques basés sur l'historique de vente.

**Fichiers créés** (Phase 3 - ~1240 lignes) :

- `services/pricing_models.py` (260 lignes) - Modèles Pydantic
- `services/pricing_engine.py` (300 lignes) - Moteur CAS 1/2/3/4
- `services/sap_history_service.py` (250 lignes) - Accès historiques SAP
- `services/pricing_audit_db.py` (280 lignes) - Base audit SQLite
- `services/transport_calculator.py` (150 lignes) - Calculateur transport Phase 1

### Phase 4 : Enrichissement & Validation ⭐ NOUVEAU

Workflow de validation commerciale complet avec dashboard métriques temps réel, taux de change et remises fournisseurs.

**Fichiers créés** (Phase 4 - ~2150 lignes) :

- `services/validation_models.py` (320 lignes) - Modèles workflow validation
- `services/quote_validator.py` (450 lignes) - Service validation commerciale
- `routes/routes_pricing_validation.py` (180 lignes) - 12 endpoints API validation
- `services/dashboard_service.py` (340 lignes) - Métriques temps réel
- `services/currency_service.py` (200 lignes) - Taux de change (EUR, USD, GBP, CHF)
- `services/supplier_discounts_db.py` (460 lignes) - Remises fournisseurs

**Fichiers modifiés** :

- `services/pricing_engine.py` - Intégration validation automatique
- `main.py` - Enregistrement routes `/api/validations`

**Fonctionnalités Phase 4** :

- ✅ Validation commerciale automatique (CAS 2 & 4)
- ✅ Priorités auto (URGENT > 20%, HIGH > 10%, MEDIUM, LOW)
- ✅ Expirations automatiques (4h urgent, 48h normal)
- ✅ Dashboard métriques temps réel (pricing + validation)
- ✅ Service taux de change avec cache (4h)
- ✅ Remises fournisseurs (PERCENTAGE, FIXED_AMOUNT)
- ✅ 12 endpoints API validation

**Bénéfices Globaux** :

- ✅ Calcul prix automatique intelligent (4 CAS)
- ✅ Validation commerciale workflow complet
- ✅ Traçabilité exhaustive de chaque décision
- ✅ Alertes commerciales pour variations importantes
- ✅ Dashboard métriques temps réel
- ✅ Support multi-devises (EUR, USD, GBP, CHF)
- ✅ Réduction temps traitement : 15-20 min → < 2 min
- ✅ Taux succès pricing intelligent : > 80% (CAS 1 + CAS 3)
- ✅ Taux validation manuelle : < 20% (CAS 2 + CAS 4)

**Voir documentation complète** : `IMPLEMENTATION_PHASE1_COMPLETE.md`
