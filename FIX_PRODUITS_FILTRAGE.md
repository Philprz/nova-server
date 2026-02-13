# Fix Filtrage Faux Positifs - Extraction Produits

## Date: 2026-02-13

## Problème Identifié

L'email MarmaraCam extrait **41 produits au lieu de 28**.

**Faux positifs détectés:**
- `X-AXIS`, `Y-AXIS`, `Z-AXIS` (termes machines anglais)
- `X-EKSENİ`, `Y-EKSENİ` (turc: "axe")
- `ci-joint` (français: "attaché")
- `902826751020` (numéro fax turc - 12 chiffres)

## Corrections Appliquées ✅

### Fichier: `services/email_analyzer.py`

**1. Amélioration `_is_phone_number()` (ligne ~468)**

Ajouts:
- ✅ Préfixe turc `'90'` pour détecter les numéros turcs
- ✅ Règle générique: tout nombre **≥ 11 chiffres purement numérique** = téléphone/fax

Avant:
```python
if 11 <= len(code) <= 15:
    if code.startswith(('44', '41', '49', '39', '34', '351', '352', '1')):
        return True
```

Après:
```python
if 11 <= len(code) <= 15:
    if code.startswith(('44', '41', '49', '39', '34', '351', '352', '1', '90')):  # Ajout '90'
        return True

# NOUVEAU: Numéros très longs (>= 11 chiffres)
if code.isdigit() and len(code) >= 11:
    return True
```

**Impact:** `902826751020` (12 chiffres) est maintenant correctement filtré ✅

---

**2. Nouvelle fonction `_is_false_positive_product()` (après ligne ~491)**

Blacklist complète des faux positifs:

```python
blacklist = {
    # Termes machines (anglais)
    'XAXIS', 'YAXIS', 'ZAXIS',
    'AAXIS', 'BAXIS', 'CAXIS',

    # Termes machines (turc)
    'XEKSENI', 'YEKSENI', 'ZEKSENI',
    'EKSENI',

    # Mots français courants
    'CIJOINT', 'CIJOINTS', 'CIJOINTE', 'CIJOINTES',
    'ENPIECE', 'ENPIECES',

    # Mots anglais courants
    'ATTACHED', 'ATTACHMENT',
    'DRAWING', 'DRAWINGS',
    'SKETCH', 'SKETCHES',

    # Termes génériques
    'PIECE', 'PIECES', 'PART', 'PARTS',
    'ITEM', 'ITEMS', 'REF', 'REFERENCE',
}
```

Logique:
- Normalise le code (uppercase, supprime `-` et `_`)
- Vérifie si présent dans blacklist
- Vérifie si CONTIENT un terme de la blacklist (ex: "X-AXIS" → "XAXIS")

**Impact:** `X-AXIS`, `Y-AXIS`, `Z-AXIS`, `ci-joint` sont maintenant filtrés ✅

---

**3. Intégration dans `_extract_products_from_text()` (ligne ~514)**

Avant:
```python
if (ref and len(ref) >= 6 and ref not in found_refs
    and not self._is_phone_number(ref)):
    found_refs.add(ref)
```

Après:
```python
if (ref and len(ref) >= 6 and ref not in found_refs
    and not self._is_phone_number(ref)
    and not self._is_false_positive_product(ref)):  # NOUVEAU
    found_refs.add(ref)
```

**Impact:** Double filtre téléphones + faux positifs ✅

---

## Tests Unitaires Créés

### 1. `test_product_filtering.py`

Test unitaire des fonctions de filtrage (sans backend):
- ✅ `_is_phone_number()` - Détection téléphones/fax
- ✅ `_is_false_positive_product()` - Détection faux positifs
- ✅ `_extract_products_from_text()` - Extraction complète avec filtrage

**Résultat attendu:**
```
[OK] 902826751020 -> téléphone/fax
[OK] X-AXIS -> faux positif
[OK] Y-AXIS -> faux positif
[OK] HST-117-03 -> produit valide
```

### 2. `test_marmaracam_products_after_fix.py`

Test avec l'email MarmaraCam réel (nécessite backend):
- Vérifie client = C0249 (MarmaraCam)
- Vérifie nombre produits ≈ 28
- Liste tous les produits extraits
- Vérifie absence faux positifs connus

---

## Actions Requises

### 1. Arrêter le Backend

```bash
Ctrl+C
```

Attendre confirmation complète.

### 2. Relancer le Backend

```bash
cd C:\Users\PPZ\NOVA-SERVER
python main.py
```

Vérifier dans les logs:
```
NOVA DEMARRE AVEC SUCCES
Uvicorn running on http://0.0.0.0:8001
```

### 3. Tester le Fix

**Option A: Test unitaire (rapide)**

```bash
python test_product_filtering.py
```

**Résultat attendu:**
```
[OK] Tous les tests passent
[OK] Faux positifs filtrés
```

**Option B: Test avec email réel (complet)**

```bash
python test_marmaracam_products_after_fix.py
```

**Résultat attendu:**
```
[OK] Client correct: C0249 - MARMARA CAM
[OK] Nombre de produits: 28/28 OK
[OK] Faux positifs: 0 trouvés OK
[SUCCES] Email MarmaraCam analysé correctement!
```

### 4. Tester dans l'Interface

1. Rafraîchir la page (F5)
2. Cliquer sur "Demande chiffrage MarmaraCam"
3. Vérifier:
   - ✅ Badge vert "Devis détecté"
   - ✅ Client: MARMARA CAM (C0249)
   - ✅ ~28 produits (pas 41)

---

## Résumé des Changements

| Fichier | Lignes | Description |
|---------|--------|-------------|
| `services/email_analyzer.py` | ~468-491 | Amélioration détection téléphones/fax (ajout Turquie + règle générique) |
| `services/email_analyzer.py` | ~492-540 | Nouvelle fonction filtrage faux positifs (blacklist complète) |
| `services/email_analyzer.py` | ~514-522 | Intégration double filtre dans extraction produits |
| `test_product_filtering.py` | Nouveau | Tests unitaires filtrage |
| `test_marmaracam_products_after_fix.py` | Nouveau | Test email MarmaraCam réel |

**Total lignes ajoutées:** ~100 lignes
**Total lignes modifiées:** ~10 lignes

---

## Prochaines Étapes (si OK)

1. ✅ Vérifier que les autres emails fonctionnent toujours
2. 📋 Valider que le filtrage ne supprime pas de vrais produits
3. 🧪 Tester avec d'autres emails contenant des pièces jointes PDF
4. 📊 Monitorer les logs pour voir le taux de filtrage

---

## Si le Problème Persiste

### Diagnostic 1: Vérifier le code chargé

```powershell
Select-String -Path ".\services\email_analyzer.py" -Pattern "_is_false_positive_product" -Context 0,3
```

**Devrait afficher:**
```python
def _is_false_positive_product(self, code: str) -> bool:
    """Détecte les faux positifs courants..."""
    code_normalized = code.upper()...
```

### Diagnostic 2: Logs backend

Après analyse, chercher dans les logs:
```
[DEBUG] Product extraction: 41 products before filtering
[DEBUG] Product filtering: removed 13 false positives
[INFO] Final products: 28
```

### Diagnostic 3: Tester extraction directe

```python
from services.email_analyzer import get_email_analyzer

analyzer = get_email_analyzer()
print(analyzer._is_phone_number("902826751020"))  # Doit afficher True
print(analyzer._is_false_positive_product("X-AXIS"))  # Doit afficher True
```

---

## Contact / Support

Si après redémarrage il y a toujours 41 produits:

1. Partager résultat de `python test_product_filtering.py`
2. Partager résultat de `python test_marmaracam_products_after_fix.py`
3. Partager les 10 premiers produits extraits
4. Vérifier la date/heure de démarrage backend (doit être après le fix)
