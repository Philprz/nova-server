# Résumé Session - Matching Intelligent Produits

**Date:** 2026-02-12
**Durée:** ~3 heures
**Objectif:** Implémenter le matching intelligent avec apprentissage automatique pour les références fournisseurs

---

## ✅ RÉALISATIONS

### 1. **Problème MarmaraCam Résolu**
- ✅ "MarmaraCam" (sans espace) → Matche maintenant "MARMARA CAM" (C0249) avec score 88
- ✅ Stratégie de matching compact par segments implémentée
- ✅ Blacklist mots communs (évite faux positifs comme "devis" → "DEVI")

### 2. **Base de Données Apprentissage**
- ✅ Table `product_code_mapping` créée (supplier_tariffs.db)
- ✅ Service `ProductMappingDB` complet ([product_mapping_db.py](services/product_mapping_db.py))
- ✅ Méthodes: get_mapping(), save_mapping(), validate_mapping(), get_statistics()

### 3. **Stratégie en Cascade 3 Niveaux**
- ✅ Niveau 1: Match exact ItemCode SAP (score 100)
- ✅ Niveau 2: Recherche dans table apprentissage (score 95)
- ✅ Niveau 3: Fuzzy match ItemName + description (score 60-90)
- ✅ Niveau 4: Enregistrement comme PENDING pour création

### 4. **Extraction Intelligente PDF**
- ✅ Extraction codes SHEPPEE: HST-117-03, TRI-037, C315-6305RS ✅
- ✅ Extraction descriptions associées: "SIZE 3 PUSHER BLADE", etc. ✅
- ✅ Support patterns: "SHEPPEE CODE: XXX - DESC", "Row X: CODE - DESC"
- ✅ Filtrage doublons (garde version complète "C315-6305RS" vs "C315")

### 5. **Méthode Matching Intelligent**
- ✅ `_match_single_product_intelligent()` implémentée
- ✅ Intégration dans `_match_products()`
- ✅ Passage supplier_card_code pour apprentissage contextuel

### 6. **Documentation Complète**
- ✅ [PRODUCT_MATCHING_STRATEGY.md](PRODUCT_MATCHING_STRATEGY.md) - Guide complet
- ✅ [MATCHING_IMPROVEMENTS.md](MATCHING_IMPROVEMENTS.md) - Corrections MarmaraCam

---

## ⚠️ PROBLÈMES IDENTIFIÉS

### 1. **Fuzzy Matching Trop Permissif**

**Symptôme:**
```
Codes attendus: HST-117-03, TRI-037, C315-6305RS (SHEPPEE)
↓
Résultat: IM30043, A12763, A04010 (produits SAP incorrects)
Raison: "Nom similaire (substring)" - score 85
```

**Cause:**
- Description "BALL BEARING" matche avec produit SAP contenant "BEARING"
- Description "LIFT ROLLER STUD" matche avec produit contenant "ROLLER"
- Score 85 considéré comme valide → produit retourné

**Impact:**
- Les codes fournisseur SHEPPEE ne sont PAS enregistrés pour création
- Des produits SAP incorrects sont proposés à la place

### 2. **Comportement Attendu vs Réel**

| Situation | Comportement Attendu | Comportement Réel |
|-----------|---------------------|-------------------|
| Code SHEPPEE non dans SAP | `not_found_in_sap=True`, score=0, PENDING création | Fuzzy match → produit SAP incorrect, score=85 |
| Description "BALL BEARING" | Enregistrer pour validation manuelle | Match produit SAP avec "BEARING" |

---

## 🔧 CORRECTIONS NÉCESSAIRES

### Option A: Augmenter Seuil Fuzzy Match
```python
# Dans _match_single_product_intelligent()
# Ligne ~530

if best_match and best_score >= 90:  # Était: >= 70
    # Enregistrer mapping
else:
    # Marquer comme not_found_in_sap
```

**Impact:** Seuls les matchs très précis (≥ 90) sont acceptés

### Option B: Mode Strict pour Fournisseurs Spécifiques
```python
# Si supplier = SHEPPEE ou autre fournisseur externe
# Ne faire QUE du match exact, pas de fuzzy
if supplier_is_external:
    fuzzy_match_enabled = False
```

**Impact:** Codes fournisseurs toujours enregistrés pour création

### Option C: Validation Manuelle Obligatoire < 95
```python
if best_score < 95:
    status = "PENDING"  # Nécessite validation commerciale
else:
    status = "VALIDATED"  # Auto-approuvé
```

**Impact:** Commercial valide tous les fuzzy match avant usage

---

## 📊 RÉSULTATS TESTS

### Test MarmaraCam (3 produits SHEPPEE)

**Extraction:**
- ✅ Codes extraits: HST-117-03, TRI-037, C315-6305RS
- ✅ Descriptions extraites: "SIZE 3 PUSHER BLADE CARBON", "LIFT ROLLER STUD", "BALL BEARING"

**Matching:**
- ❌ HST-117-03 → IM30043 (incorrect, fuzzy match score 85)
- ❌ TRI-037 → A12763 (incorrect, fuzzy match score 85)
- ❌ C315-6305RS → A04010 (incorrect, fuzzy match score 85)

**Attendu:**
- ✅ HST-117-03 → not_found_in_sap=True, status=PENDING
- ✅ TRI-037 → not_found_in_sap=True, status=PENDING
- ✅ C315-6305RS → not_found_in_sap=True, status=PENDING

---

## 🚀 RECOMMANDATIONS

### Immédiat (Correction Urgente)
1. **Appliquer Option A** - Augmenter seuil fuzzy à 90%
2. **Tester avec PDF complet** Marmara Cam (28 produits)
3. **Vérifier enregistrement PENDING** dans product_code_mapping

### Court Terme (Cette Semaine)
1. **Créer Routes API Validation** ([routes/routes_product_validation.py](routes/routes_product_validation.py))
2. **Créer Service Création SAP** ([services/sap_product_creator.py](services/sap_product_creator.py))
3. **Dashboard React Validation** Page `/validation/products`

### Moyen Terme (Semaine Prochaine)
1. **Auto-génération Codes RONDOT** (ex: "RONDOT-TRI037")
2. **Workflow Validation Commerciale** (Approuver/Rejeter/Créer)
3. **Tests End-to-End** avec vrais emails

---

## 📁 FICHIERS CRÉÉS

1. ✅ `services/product_mapping_db.py` (300 lignes) - Base apprentissage
2. ✅ `services/email_matcher.py` (modifié) - Stratégie cascade + extraction
3. ✅ `PRODUCT_MATCHING_STRATEGY.md` - Documentation complète
4. ✅ `MATCHING_IMPROVEMENTS.md` - Corrections MarmaraCam
5. ✅ Tests: `test_marmara_pdf_intelligent.py`, `test_matching_quick.py`, etc.

---

## 📝 PROCHAINE SESSION

**Commencer par:**
```python
# 1. Corriger le seuil fuzzy (Option A)
# services/email_matcher.py ligne ~530
if best_match and best_score >= 90:  # Changé de 70 à 90

# 2. Tester avec PDF Marmara Cam complet
python test_marmara_pdf_intelligent.py

# 3. Vérifier table mapping
python -c "from services.product_mapping_db import get_product_mapping_db; print(get_product_mapping_db().get_statistics())"
```

**Puis créer:**
1. Routes API validation
2. Service création produits SAP
3. Dashboard React

---

## 💡 LEÇONS APPRISES

1. **Fuzzy matching nécessite calibration** - Trop permissif = faux positifs
2. **Cas d'usage fournisseur ≠ cas d'usage interne** - Codes externes doivent être enregistrés, pas matchés approximativement
3. **Apprentissage automatique puissant MAIS** - Nécessite validation humaine la première fois
4. **Tests avec données réelles critiques** - Mock ne révèle pas les vrais problèmes

---

**Status:** ⚠️ Implémentation complète mais nécessite calibration du fuzzy matching avant production

**Prochaine étape:** Appliquer Option A (seuil 90%) et tester avec 28 produits Marmara Cam
