# QuoteWorkflowEngine - Moteur de Workflow Déterministe RONDOT

**Fichier :** `services/quote_workflow_engine.py`
**Version :** 1.0.0
**Date :** 07/02/2026

## 📋 Vue d'Ensemble

Le `QuoteWorkflowEngine` est une **machine à états déterministe** qui orchestre le processus complet de génération de devis selon les règles métier strictes de RONDOT-SAS.

### Principes Fondamentaux

✅ **Déterministe** : Même entrée → Même sortie, toujours
✅ **Traçable** : Chaque décision est justifiée et loggée
✅ **Sans ML** : Aucun comportement probabiliste ou apprentissage
✅ **Règles explicites** : Toutes les règles métier sont codées en dur
✅ **Interface abstraite** : Aucun appel externe réel (SAP, email) sans interface

---

## 🔄 Machine à États (19 états)

```
RECEIVED
    ↓
CLIENT_IDENTIFIED / CLIENT_CREATED
    ↓
PRODUCT_IDENTIFIED
    ↓
SUPPLIER_IDENTIFIED
    ↓
SUPPLIER_PRICED
    ↓
HISTORICAL_ANALYSIS_DONE
    ↓
PRICING_CASE_SELECTED (CAS 1/2/3/4)
    ↓
CURRENCY_APPLIED
    ↓
SUPPLIER_DISCOUNT_APPLIED
    ↓
MARGIN_APPLIED
    ↓
PRICING_INTELLIGENT_DONE
    ↓
TRANSPORT_OPTIMIZED
    ↓
JUSTIFICATION_BUILT
    ↓
COHERENCE_VALIDATED
    ↓
QUOTE_GENERATED
    ↓
MANUAL_VALIDATION_REQUIRED (si requis)
    OU
QUOTE_SENT
```

---

## 📊 Règles Métier Implémentées

### R1 - Client

- Recherche client dans SAP
- Si absent → **création obligatoire** (blocante)
- État : `CLIENT_IDENTIFIED` ou `CLIENT_CREATED`

### R2 - Produit & Fournisseur

- Identification produits depuis SAP ou fichiers fournisseurs
- **RÈGLE STRICTE** : 1 produit = 1 fournisseur
- État : `PRODUCT_IDENTIFIED` → `SUPPLIER_IDENTIFIED`

### R3 - Pricing Intelligent (Arbre de décision)

#### Question 1 : Historique vente à CE client ?

- **NON** → Question 2
- **OUI** → Question 3

#### Question 2 : Vendu à d'autres clients ?

- **NON** → **CAS 4 : NOUVEAU PRODUIT** ⚠️ Validation requise
- **OUI** → **CAS 3 : PRIX MOYEN AUTRES CLIENTS**

#### Question 3 : Prix fournisseur stable (<5%) ?

- **OUI** → **CAS 1 : MAINTIEN PRIX** (Historique Client - Stable)
- **NON** → **CAS 2 : RECALCUL PRIX** ⚠️ Validation requise (Historique Client - Modifié)

**État :** `PRICING_CASE_SELECTED` → `PRICING_INTELLIGENT_DONE`

#### Détails des CAS

| CAS | Nom | Condition | Décision | Validation |
|-----|-----|-----------|----------|------------|
| CAS 1 (HC) | Historique Client - Stable | Article vendu à ce client + prix stable (<5%) | Reprendre prix dernière vente | ❌ Non |
| CAS 2 (HCM) | Historique Client - Modifié | Article vendu à ce client + prix modifié (≥5%) | Recalculer avec marge 45% + Alerte | ✅ **OUI** |
| CAS 3 (HA) | Historique Autres | Jamais vendu à ce client, vendu à autres | Prix moyen pondéré | ❌ Non* |
| CAS 4 (NP) | Nouveau Produit | Jamais vendu nulle part | Prix fournisseur + marge 45% | ✅ **OUI** |

*Validation requise si < 3 ventes de référence

### R4 - Marges

- **Marge standard** : 45%
- **Marge ajustable** : 35% à 45%
- **Formule stricte** : `PV = prix_net / (1 - marge)`

**État :** `MARGIN_APPLIED`

### R5 - Devises

- Si devise fournisseur ≠ EUR → Application taux du jour
- Taux fourni par `CurrencyService`
- Taux loggé dans la traçabilité

**État :** `CURRENCY_APPLIED`

### R6 - Transport

- Calcul poids total = Σ(poids unitaire × quantité)
- Comparaison transporteurs : coût, délai, fiabilité
- 1 transporteur recommandé + alternatives
- Aucune sélection implicite

**État :** `TRANSPORT_OPTIMIZED`

### R7 - Pricing Intelligent (NON ML)

✅ Ajustements par règles explicites basés sur :
- Historique client
- Typologie produit

❌ **Interdit** :
- Scoring
- Prédiction
- Apprentissage automatique

### R8 - Traçabilité

Création d'un **bloc justification** contenant :
- Stratégie pricing appliquée (CAS 1/2/3/4)
- Sources de données utilisées
- Historique référencé
- Marge calculée
- Transport retenu
- Alertes éventuelles
- Validation requise (oui/non) + raison

**État :** `JUSTIFICATION_BUILT`

### R9 - Validation Humaine

Validation manuelle **OBLIGATOIRE** si :
- **CAS 2** : Variation prix fournisseur ≥ 5%
- **CAS 4** : Nouveau produit jamais vendu
- **Ajustement manuel** : Prix modifié manuellement

**État :** `MANUAL_VALIDATION_REQUIRED`

---

## 🔧 Utilisation

### Exemple de Base

```python
from services.quote_workflow_engine import (
    QuoteWorkflowEngine,
    QuoteRequest,
    Product
)

# Créer demande de devis
request = QuoteRequest(
    request_id="REQ_001",
    client_name="ACME Corporation",
    client_email="acme@example.com",
    products=[
        Product(
            item_code="PROD_001",
            item_name="Widget Premium",
            quantity=100.0,
            weight_kg=2.5
        )
    ],
    source="EMAIL"
)

# Exécuter workflow
engine = QuoteWorkflowEngine()
draft = await engine.run(request)

# Résultat
print(f"État : {draft.current_state}")
print(f"Total HT : {draft.total_ht_eur:.2f} EUR")
print(f"Validation requise : {draft.requires_manual_validation}")

# Traçabilité
for trace in draft.traces:
    print(f"[{trace.state}] {trace.decision}")
    print(f"  Justification: {trace.justification}")
    print(f"  Sources: {', '.join(trace.data_sources)}")

# Justification complète
print(draft.justification_block)
```

### Workflow avec Validation Manuelle

```python
draft = await engine.run(request)

if draft.requires_manual_validation:
    print("⚠️ VALIDATION COMMERCIALE REQUISE")
    for reason in draft.validation_reasons:
        print(f"  - {reason}")

    # État : MANUAL_VALIDATION_REQUIRED
    # Le devis n'est PAS envoyé automatiquement
    # Attente validation commerciale
else:
    # État : QUOTE_SENT
    # Devis envoyé automatiquement
    print("✓ Devis envoyé")
```

---

## 📦 Objets Principaux

### QuoteRequest
Demande de devis entrante

```python
@dataclass
class QuoteRequest:
    request_id: str
    client_name: Optional[str]
    client_code: Optional[str]
    client_email: Optional[str]
    products: List[Product]
    source: str  # EMAIL | API | MANUAL
    raw_data: Optional[Dict]
```

### Product
Produit commandé

```python
@dataclass
class Product:
    item_code: str
    item_name: str
    quantity: float
    unit: str = "PCE"
    weight_kg: Optional[float]
    dimensions: Optional[str]
    source: str  # SAP | SUPPLIER
```

### Client
Client identifié ou créé

```python
@dataclass
class Client:
    card_code: str
    card_name: str
    email: Optional[str]
    phone: Optional[str]
    address: Optional[str]
    siret: Optional[str]
    is_new: bool
    source: str  # SAP | CREATED
```

### QuoteDraft
Devis généré avec traçabilité complète

```python
@dataclass
class QuoteDraft:
    quote_id: str
    client: Optional[Client]
    products: List[Product]
    suppliers: List[Supplier]
    price_contexts: Dict[str, PriceContext]
    transport_options: List[TransportOption]
    selected_transport: Optional[TransportOption]

    total_products_eur: float
    total_transport_eur: float
    total_ht_eur: float
    total_ttc_eur: float

    current_state: WorkflowState
    traces: List[DecisionTrace]

    requires_manual_validation: bool
    validation_reasons: List[str]

    justification_block: str
    created_at: datetime
    updated_at: datetime
```

### DecisionTrace
Trace d'une décision

```python
@dataclass
class DecisionTrace:
    state: WorkflowState
    timestamp: datetime
    decision: str
    justification: str
    data_sources: List[str]
    alerts: List[str]
```

---

## 🔗 Intégrations

### Services Utilisés

| Service | Rôle | Fichier |
|---------|------|---------|
| `PricingEngine` | Calcul pricing CAS 1/2/3/4 | `services/pricing_engine.py` |
| `QuoteValidator` | Validation commerciale | `services/quote_validator.py` |
| `CurrencyService` | Taux de change | `services/currency_service.py` |
| `SupplierDiscountsDB` | Remises fournisseurs | `services/supplier_discounts_db.py` |
| `TransportCalculator` | Calcul transport | `services/transport_calculator.py` |
| `SAPHistoryService` | Historiques ventes/achats | `services/sap_history_service.py` |

### Singleton

```python
from services.quote_workflow_engine import get_quote_workflow_engine

engine = get_quote_workflow_engine()
```

---

## ✅ Tests

**Fichier :** `tests/test_quote_workflow_engine.py`

```bash
# Exécuter tests
python tests/test_quote_workflow_engine.py
```

**Tests inclus :**
1. Workflow complet (client nouveau, 2 produits)
2. CAS 2 avec validation manuelle

---

## 📊 Exemple de Sortie

### Justification Block

```
═══════════════════════════════════════════════════
JUSTIFICATION DEVIS - TRAÇABILITÉ COMPLÈTE
═══════════════════════════════════════════════════

Devis ID : 550e8400-e29b-41d4-a716-446655440000
Client : Société Test SARL (C_NEW_001)
Date : 07/02/2026 10:30

--- PRODUITS ---

Article : Produit Test 1 (PROD_001)
Quantité : 10.0 PCE

  Stratégie pricing : CAS_4_NP
  Justification : Nouveau produit jamais vendu
  Prix fournisseur : 100.00 EUR
  Taux change : 1.0
  Remise fournisseur : 0.0%
  Prix net fournisseur : 100.00 EUR
  Marge appliquée : 45.0%
  Prix calculé : 181.82 EUR
  ⚠️ VALIDATION REQUISE : Nouveau produit - validation commerciale obligatoire

--- TRANSPORT ---
Transporteur : Standard
Coût transport : 25.00 EUR
Délai : 3 jours

--- TOTAUX ---
Total produits HT : 1818.20 EUR
Total transport : 25.00 EUR
TOTAL HT : 1843.20 EUR
TOTAL TTC (20%) : 2211.84 EUR

═══════════════════════════════════════════════════
⚠️ VALIDATION COMMERCIALE REQUISE
═══════════════════════════════════════════════════
  - PROD_001 : Nouveau produit - validation commerciale obligatoire

═══════════════════════════════════════════════════
Toutes les décisions sont traçables et déterministes
Aucun comportement probabiliste ou ML appliqué
═══════════════════════════════════════════════════
```

---

## 🚨 Points d'Attention

### Interfaces Abstraites

Le workflow utilise des **interfaces abstraites** pour :
- Recherche/création client SAP → TODO implémentation réelle
- Récupération prix fournisseurs → TODO implémentation réelle
- Création devis SAP → TODO implémentation réelle
- Envoi email → TODO implémentation réelle

Ces interfaces peuvent être remplacées par des implémentations réelles ou des mocks selon l'environnement.

### Erreurs SAP

Les erreurs SAP (ex: `DocumentLines` non expandable) sont gérées par fallback :
- Si historique SAP inaccessible → CAS 4 (Nouveau Produit) par défaut
- Alerte générée dans les traces

### Performance

- Cache historique SAP recommandé (TTL 1h)
- Appels SAP parallélisables pour plusieurs produits
- Timeout SAP : 10 secondes par défaut

---

## 📚 Documentation Liée

- [PHASE_3_4_VERIFICATION.md](PHASE_3_4_VERIFICATION.md) - Vérification complète Phase 3 & 4
- [README.md](README.md) - Documentation générale NOVA-SERVER
- [MEMORY.md](.claude/projects/.../memory/MEMORY.md) - Historique développement

---

## 🔄 Version

**v1.0.0** (07/02/2026)
- Implémentation initiale
- 19 états de workflow
- 9 règles métier strictes
- Traçabilité complète
- Sans ML ni comportement probabiliste

---

## 📝 Licence

Propriété de RONDOT-SAS
Usage interne uniquement
