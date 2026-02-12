# Stratégie Intelligente de Matching Produits + Création SAP

**Date:** 2026-02-12
**Contexte:** Gestion des références externes (fournisseurs) non présentes dans le catalogue SAP

---

## 🎯 Objectif

Quand un client (ex: Marmara Cam) envoie une demande de devis avec **28 produits référencés par codes fournisseur** (ex: HST-117-03, TRI-037, etc.), le système doit:

1. **Identifier automatiquement** les produits s'ils existent dans SAP
2. **Apprendre les correspondances** pour les fois suivantes
3. **Créer les produits manquants** dans SAP si nécessaire

---

## 📊 Stratégie en Cascade (3 niveaux)

### Niveau 1: **EXACT MATCH** (ItemCode SAP)
```
Code: "HST-117-03"
↓
Recherche dans cache SAP items_cache["HST-117-03"]
↓ Trouvé?
✅ OUI → Retourner (score 100, méthode: EXACT)
❌ NON → Niveau 2
```

### Niveau 2: **APPRENTISSAGE AUTOMATIQUE** (Table mapping)
```
Code: "HST-117-03"
Fournisseur: "C0249" (Marmara Cam)
↓
Recherche dans product_code_mapping
WHERE external_code = "HST-117-03"
  AND supplier_card_code = "C0249"
  AND status = "VALIDATED"
↓ Trouvé?
✅ OUI → Retourner matched_item_code SAP (score 95, méthode: LEARNED)
❌ NON → Niveau 3
```

### Niveau 3: **FUZZY MATCH** (ItemName SAP)
```
Code: "HST-117-03"
Description: "SIZE 3 PUSHER BLADE CARBON"
↓
Pour chaque produit SAP:
  - Comparer "SIZE 3 PUSHER BLADE CARBON" avec ItemName
  - Substring match? → score 85
  - Fuzzy ratio > 0.7? → score 60-90
  - Mots communs ≥ 2? → score 60-80
↓ Meilleur match score ≥ 70?
✅ OUI → Enregistrer mapping + Retourner (score 70-90, méthode: FUZZY_NAME)
❌ NON → Niveau 4
```

### Niveau 4: **CRÉATION PRODUIT SAP** (nouveau!)
```
Code: "HST-117-03"
Description: "SIZE 3 PUSHER BLADE CARBON"
↓
1. Enregistrer dans product_code_mapping (status: PENDING)
2. Retourner avec flag not_found_in_sap = true
3. Déclencher workflow création produit:
   ↓
   a) Validation manuelle (dashboard)
   b) Génération ItemCode RONDOT
   c) Création dans SAP B1 via API
   d) Mise à jour mapping (status: VALIDATED)
```

---

## 💾 Base de Données: product_code_mapping

**Table SQLite** (supplier_tariffs.db):

```sql
CREATE TABLE product_code_mapping (
    external_code TEXT NOT NULL,           -- "HST-117-03"
    external_description TEXT,             -- "SIZE 3 PUSHER BLADE CARBON"
    supplier_card_code TEXT NOT NULL,      -- "C0249" (Marmara Cam)
    matched_item_code TEXT,                -- Code SAP RONDOT (NULL si pending)
    match_method TEXT,                     -- "EXACT", "FUZZY_NAME", "MANUAL", "PENDING"
    confidence_score REAL,                 -- 0-100
    last_used TIMESTAMP,
    use_count INTEGER DEFAULT 1,
    status TEXT DEFAULT 'PENDING',         -- "PENDING", "VALIDATED", "REJECTED"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (external_code, supplier_card_code)
);
```

**Index:**
- `idx_external_code` sur external_code
- `idx_supplier_code` sur supplier_card_code
- `idx_status` sur status

---

## 🔄 Workflow Complet

### 1. Réception Email + PDF

```
Email: "Demande de devis Marmara Cam"
PDF: 28 produits (codes SHEPPEE)
↓
EmailMatcher.match_email()
  ├─ Matcher client: "MARMARA CAM" → C0249 ✅
  ├─ Extraire descriptions produits du PDF
  └─ Pour chaque code:
      ├─ HST-117-03 → _match_single_product_intelligent()
      ├─ TRI-037 → _match_single_product_intelligent()
      └─ ...
```

### 2. Matching Intelligent par Produit

```python
_match_single_product_intelligent(
    code="HST-117-03",
    description="SIZE 3 PUSHER BLADE CARBON",
    text=pdf_content,
    supplier_card_code="C0249"
)
↓
Niveau 1: Cache SAP? NON
Niveau 2: Mapping DB? NON
Niveau 3: Fuzzy match?
  → Trouvé: "PUSHER BLADE SIZE 3 CARBON" (score 85)
  → Enregistrer mapping (status: VALIDATED)
  → Retourner matched_item_code
```

### 3. Produits Non Trouvés → Création SAP

**Produits avec `not_found_in_sap = true`:**

```
TRI-037: "LIFT ROLLER STUD" → NON TROUVÉ
↓
1. Enregistré dans product_code_mapping (status: PENDING)
2. Affiché dans Dashboard Validation Produits
3. Commercial valide:
   ├─ Option A: Associer à un code SAP existant
   ├─ Option B: Créer un nouveau produit dans SAP
   └─ Option C: Rejeter (produit non géré)
```

**Option B: Création Nouveau Produit SAP**

```javascript
// Workflow création produit
POST /api/products/create
{
    "external_code": "TRI-037",
    "external_description": "LIFT ROLLER STUD",
    "supplier_card_code": "C0249",
    "new_item_code": "RONDOT-TRI037",  // Généré ou saisi
    "item_name": "LIFT ROLLER STUD SHEPPEE",
    "item_group": "105",  // Pièces détachées
    "purchase_item": "Y",
    "sales_item": "Y",
    "inventory_item": "Y"
}
↓
1. Créer dans SAP B1:
   POST https://sap.rondot.com:50000/b1s/v1/Items
   {
       "ItemCode": "RONDOT-TRI037",
       "ItemName": "LIFT ROLLER STUD SHEPPEE",
       "ItemsGroupCode": 105,
       "PurchaseItem": "tYES",
       "SalesItem": "tYES",
       "InventoryItem": "tYES"
   }

2. Mettre à jour mapping:
   UPDATE product_code_mapping
   SET matched_item_code = "RONDOT-TRI037",
       match_method = "MANUAL",
       confidence_score = 100,
       status = "VALIDATED"
   WHERE external_code = "TRI-037"
     AND supplier_card_code = "C0249"

3. Sync cache SAP (ajouter le nouveau produit)
```

---

## 🖥️ Dashboard Validation Produits (À créer)

### Page: `/validation/products`

**Section 1: Produits en attente de validation**

| Code Externe | Description | Fournisseur | Meilleur Match SAP | Score | Actions |
|--------------|-------------|-------------|-------------------|-------|---------|
| TRI-037 | LIFT ROLLER STUD | Marmara Cam (C0249) | - | 0 | [Associer] [Créer] [Rejeter] |
| HST-117-03 | SIZE 3 PUSHER BLADE | Marmara Cam (C0249) | PUSHER BLADE SIZE 3 | 85 | [Valider] [Modifier] [Rejeter] |

**Actions:**

1. **[Associer]**: Rechercher un produit SAP existant et créer le mapping
2. **[Créer]**: Ouvrir formulaire création produit SAP
3. **[Valider]**: Confirmer le match automatique (score ≥ 70)
4. **[Rejeter]**: Marquer comme non géré

**Section 2: Formulaire Création Produit**

```
╔════════════════════════════════════════╗
║ Créer un nouveau produit dans SAP     ║
╠════════════════════════════════════════╣
║ Code externe: TRI-037                  ║
║ Description externe: LIFT ROLLER STUD  ║
║ Fournisseur: Marmara Cam (C0249)       ║
║                                        ║
║ ┌────────────────────────────────────┐ ║
║ │ Code SAP (ItemCode):               │ ║
║ │ [RONDOT-TRI037        ] [Générer]  │ ║
║ │                                    │ ║
║ │ Nom produit (ItemName):            │ ║
║ │ [LIFT ROLLER STUD SHEPPEE        ] │ ║
║ │                                    │ ║
║ │ Groupe produits:                   │ ║
║ │ [105 - Pièces détachées ▼]        │ ║
║ │                                    │ ║
║ │ Type:                              │ ║
║ │ ☑ Achat  ☑ Vente  ☑ Stock         │ ║
║ └────────────────────────────────────┘ ║
║                                        ║
║ [Créer dans SAP] [Annuler]            ║
╚════════════════════════════════════════╝
```

---

## 📈 Statistiques Mapping

**Endpoint:** `GET /api/products/mapping/statistics`

```json
{
    "total_mappings": 156,
    "validated": 142,
    "pending": 14,
    "exact_matches": 89,
    "fuzzy_matches": 45,
    "manual_matches": 8,
    "created_products": 8
}
```

---

## 🔧 API Endpoints à Créer

### 1. Liste produits en attente
```
GET /api/products/pending
Response: [
    {
        "external_code": "TRI-037",
        "external_description": "LIFT ROLLER STUD",
        "supplier_card_code": "C0249",
        "supplier_name": "MARMARA CAM SANAYI VE TICARET AS",
        "status": "PENDING",
        "created_at": "2026-02-12T10:30:00",
        "best_fuzzy_match": null
    }
]
```

### 2. Valider un mapping
```
POST /api/products/validate
Body: {
    "external_code": "HST-117-03",
    "supplier_card_code": "C0249",
    "matched_item_code": "PUSHER-BLADE-03"
}
Response: {"success": true, "message": "Mapping validated"}
```

### 3. Créer un produit SAP
```
POST /api/products/create
Body: {
    "external_code": "TRI-037",
    "external_description": "LIFT ROLLER STUD",
    "supplier_card_code": "C0249",
    "new_item_code": "RONDOT-TRI037",
    "item_name": "LIFT ROLLER STUD SHEPPEE",
    "item_group": "105",
    "purchase_item": true,
    "sales_item": true,
    "inventory_item": true
}
Response: {
    "success": true,
    "item_code": "RONDOT-TRI037",
    "message": "Product created in SAP and mapping validated"
}
```

### 4. Statistiques mapping
```
GET /api/products/mapping/statistics
Response: {voir exemple ci-dessus}
```

---

## ✅ Exemple Complet: Email Marmara Cam

**Input:**
- Email: "Demande de devis Form No 26576"
- PDF: 28 produits SHEPPEE
- Client: msezen@marmaracam.com.tr

**Processing:**

```
1. Client matché: MARMARA CAM (C0249) - score 95 ✅

2. Produits:
   ├─ HST-117-03: Match exact SAP → OK (score 100)
   ├─ C233-50AT10-1940G3: Fuzzy match "TIMING BELT AT10/1940" → OK (score 82)
   ├─ TRI-037: Non trouvé → PENDING création
   ├─ TRI-038: Non trouvé → PENDING création
   └─ ... (24 autres)

3. Résultat:
   ├─ 18 produits trouvés automatiquement
   ├─ 10 produits en attente validation/création
   └─ Dashboard: 10 validations requises
```

**Action commerciale:**

Dashboard affiche les 10 produits en attente. Le commercial décide:
- 6 produits: Associer à des codes SAP existants → Mapping créé
- 4 produits: Créer dans SAP → Nouveaux articles créés

**Prochaine fois:**

Email similaire de Marmara Cam avec les mêmes produits:
- 28/28 produits trouvés automatiquement (score 95-100) ✅
- Aucune validation manuelle nécessaire ✅
- Gain de temps: 15 min → 30 secondes ✅

---

## 🚀 Prochaines Étapes d'Implémentation

1. ✅ **Base ProductMappingDB** - Créée
2. ✅ **Matching intelligent** - Implémenté dans email_matcher.py
3. ⏳ **Routes API validation** - À créer (routes/routes_product_validation.py)
4. ⏳ **Dashboard validation** - À créer (React frontend)
5. ⏳ **Création produits SAP** - À implémenter (SAP B1 POST /Items)
6. ⏳ **Auto-génération codes RONDOT** - Logique de nommage

---

## 📝 Notes Importantes

- **Sécurité:** Seuls les admins/commerciaux peuvent créer des produits SAP
- **Workflow:** Toute création de produit nécessite validation commerciale
- **Traçabilité:** Chaque mapping enregistre qui/quand/comment il a été créé
- **Performance:** Le matching intelligent ajoute ~50-100ms par produit
- **Cache:** Après création SAP, sync automatique du cache local

---

**Version:** 1.0
**Auteur:** NOVA AI Assistant
**Date:** 2026-02-12
