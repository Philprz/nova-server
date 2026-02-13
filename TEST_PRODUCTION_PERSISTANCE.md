# Test Production - Persistance Analyses

**Date** : 2026-02-13
**Objectif** : Valider que le problème de relance est résolu

---

## Tests Unitaires

✅ **Test base de données** : `python test_persistance_db.py`
- Sauvegarde analyses : ✅ OK
- Récupération analyses : ✅ OK
- Statistiques : ✅ OK
- Suppression : ✅ OK

---

## Tests End-to-End (Serveur FastAPI)

### Prérequis

1. **Démarrer le serveur** :
   ```bash
   cd C:\Users\PPZ\NOVA-SERVER
   python main.py
   ```

2. **Vérifier que le serveur démarre** :
   - Logs doivent montrer : `"EmailAnalysisDB initialized at ..."`
   - URL : `http://localhost:8001`

---

### Test 1 : Première Analyse (Calcul + Sauvegarde)

#### Étape 1 : Accéder à l'interface

```
http://localhost:8001/
```

#### Étape 2 : Se connecter Microsoft 365

- Cliquer sur "Se connecter"
- Autoriser l'accès à la boîte mail

#### Étape 3 : Sélectionner un email

- Choisir un email contenant une demande de devis
- **Vérifier** : Bouton "Traiter" visible

#### Étape 4 : Lancer le traitement

- Cliquer sur "Traiter"
- ⏱️ Attendre 2-5 secondes

#### Étape 5 : Vérifier les logs backend

**Ce que vous DEVEZ voir dans les logs** :

```
[INFO] Analyzing email AAMk...abc123
[INFO] 💰 Calcul pricing pour X produits...
[INFO] ⚡ Phase 5 - Pricing: XXXms
[INFO] 💾 Analysis persisted to DB for AAMk...abc123  ← CRITIQUE
```

**Si vous NE voyez PAS** `💾 Analysis persisted to DB` :
- ❌ La sauvegarde n'a pas fonctionné
- Vérifier les erreurs dans les logs
- Contacter Claude pour debug

#### Étape 6 : Vérifier l'affichage frontend

**Ce que vous DEVEZ voir** :
- ✅ Client détecté avec nom
- ✅ Liste articles avec **PRIX AFFICHÉS** (pas "À calculer")
- ✅ Badges CAS (CAS_1_HC, CAS_2_HCM, etc.)
- ✅ Totaux calculés (Sous-total HT, Marge, Total HT)

**Si vous voyez "À calculer"** :
- ❌ Le pricing n'a pas fonctionné
- Vérifier `.env` : `PRICING_ENGINE_ENABLED=true`
- Vérifier les logs backend pour erreurs pricing

---

### Test 2 : Consultation (Pas de Recalcul) ⚠️ TEST CRITIQUE

#### Étape 1 : Retour inbox

- Cliquer sur "← Retour" ou naviguer vers la liste emails

#### Étape 2 : Re-cliquer sur le MÊME email

- Sélectionner l'email qui vient d'être analysé

#### Étape 3 : Vérifier les logs backend

**Ce que vous DEVEZ voir** :

```
[INFO] 📦 Analysis loaded from DB for AAMk...abc123 (NO RECOMPUTE)
```

**Ce que vous NE DEVEZ PAS voir** :

```
[INFO] 💰 Calcul pricing pour X produits...  ← NE DOIT PAS apparaître
[INFO] ⚡ Phase 5 - Pricing: XXXms           ← NE DOIT PAS apparaître
```

**Si vous voyez le recalcul** :
- ❌ Le problème N'EST PAS résolu
- La persistance ne fonctionne pas correctement
- Contacter Claude immédiatement

#### Étape 4 : Vérifier l'affichage frontend

**Ce que vous DEVEZ voir** :
- ✅ Synthèse affichée **IMMÉDIATEMENT** (< 100ms)
- ✅ Tous les prix encore présents
- ✅ Badges CAS encore présents
- ✅ Totaux corrects

#### Étape 5 : Répéter 3-4 fois

- Retour inbox → Re-cliquer email → Retour inbox → Re-cliquer email
- **CHAQUE FOIS** : Vérifier logs backend = `📦 loaded from DB` (PAS de recalcul)

---

### Test 3 : Après Redémarrage Serveur

#### Étape 1 : Arrêter le serveur

```bash
Ctrl+C
```

#### Étape 2 : Redémarrer le serveur

```bash
python main.py
```

#### Étape 3 : Accéder à l'interface

```
http://localhost:8001/
```

#### Étape 4 : Se reconnecter Microsoft 365

#### Étape 5 : Cliquer sur l'email analysé précédemment

**Ce que vous DEVEZ voir dans les logs** :

```
[INFO] 📦 Analysis loaded from DB for GET endpoint: AAMk...abc123
```

**Explication** :
- Cache mémoire vide (redémarrage)
- Mais base SQLite persiste ✅
- Analyse récupérée depuis DB

**Si vous voyez un recalcul complet** :
- ❌ La base de données n'a pas persisté
- Vérifier que `email_analysis.db` existe bien
- Contacter Claude pour debug

---

### Test 4 : Forcer Réanalyse (Si Nécessaire)

**Cas d'usage** : Prix fournisseur a changé, besoin de recalculer

#### Option A : Via URL (Dev)

```bash
curl -X POST "http://localhost:8001/api/graph/emails/AAMk...abc123/analyze?force=true"
```

#### Option B : Supprimer de la DB (Dev)

```python
from services.email_analysis_db import get_email_analysis_db
db = get_email_analysis_db()
db.delete_analysis("AAMk...abc123")
```

**Logs attendus** :

```
[INFO] 💰 Calcul pricing pour X produits...  ← Recalcul VOULU
[INFO] ⚡ Phase 5 - Pricing: XXXms
[INFO] 💾 Analysis persisted to DB for AAMk...abc123  ← Écrase ancien
```

---

## Vérification Base de Données

### Consulter les analyses sauvegardées

```bash
cd C:\Users\PPZ\NOVA-SERVER
sqlite3 email_analysis.db
```

**Commandes SQL** :

```sql
-- Lister toutes les analyses
SELECT email_id, subject, analyzed_at, has_pricing, product_count
FROM email_analysis
ORDER BY analyzed_at DESC
LIMIT 10;

-- Statistiques globales
SELECT
    COUNT(*) as total,
    SUM(is_quote_request) as quotes,
    SUM(has_pricing) as with_pricing,
    SUM(product_count) as total_products
FROM email_analysis;

-- Détail d'une analyse
SELECT analysis_result
FROM email_analysis
WHERE email_id = 'AAMk...abc123';
```

**Quitter SQLite** : `.exit`

---

## Logs à Surveiller

### ✅ Logs Normaux (Correct)

**1ère analyse** :
```
[INFO] Analyzing email AAMk...abc123
[INFO] 💰 Calcul pricing pour 5 produits...
[INFO]   ✓ CAS_1_HC: PROD001 → 15.50 EUR (marge 55%)
[INFO]   ✓ CAS_1_HC: PROD002 → 22.30 EUR (marge 52%)
[INFO] ⚡ Phase 5 - Pricing: 450ms (5/5 success)
[INFO] 💾 Analysis persisted to DB for AAMk...abc123
```

**Consultation suivante** :
```
[INFO] 📦 Analysis loaded from DB for AAMk...abc123 (NO RECOMPUTE)
```

---

### ❌ Logs Problématiques

**Recalcul à chaque consultation** :
```
[INFO] 💰 Calcul pricing pour 5 produits...  ← NE DOIT PAS apparaître
```
→ **PROBLÈME** : Persistance ne fonctionne pas

**Erreur sauvegarde** :
```
[WARNING] Could not persist analysis to DB (non-critical): [Errno 13] Permission denied
```
→ **PROBLÈME** : Permissions fichier `email_analysis.db`

**Pricing échoue** :
```
[ERROR] Pricing error for PROD001: ...
```
→ **PROBLÈME** : Pricing engine, mais **non-bloquant** (analyse continue)

---

## Checklist de Validation

### ✅ Persistance Fonctionne

- [ ] Test unitaire DB réussi (`test_persistance_db.py`)
- [ ] 1ère analyse : Log `💾 Analysis persisted to DB` visible
- [ ] Consultation : Log `📦 Analysis loaded from DB` visible
- [ ] Consultation : **PAS de recalcul** (pas de `💰 Calcul pricing`)
- [ ] Retour inbox multiple fois : Toujours `📦 loaded from DB`
- [ ] Après redémarrage serveur : Toujours `📦 loaded from DB`
- [ ] Base SQLite : Fichier `email_analysis.db` présent et non vide
- [ ] Frontend : Synthèse affichée instantanément (< 100ms)

### ✅ Pricing Fonctionne

- [ ] Prix affichés (pas "À calculer")
- [ ] Badges CAS visibles (CAS_1_HC, CAS_2_HCM, etc.)
- [ ] Totaux calculés (Sous-total HT, Marge, Total HT)
- [ ] Tooltips badges CAS affichent justification

---

## En Cas de Problème

### Problème 1 : Recalcul à Chaque Consultation

**Symptôme** : Logs montrent `💰 Calcul pricing` à chaque clic

**Cause possible** :
1. Condition `if not force` contournée
2. Base de données non accessible
3. `email_id` change entre appels

**Debug** :
```bash
# Vérifier fichier DB
ls -la email_analysis.db

# Vérifier contenu DB
sqlite3 email_analysis.db "SELECT COUNT(*) FROM email_analysis"

# Tester avec email_id fixe
python test_persistance_db.py
```

### Problème 2 : Erreur Permission Denied

**Symptôme** : `[WARNING] Could not persist analysis to DB`

**Cause** : Permissions fichier

**Solution** :
```bash
# Windows
icacls email_analysis.db /grant Everyone:F

# Ou supprimer et relancer serveur (recrée auto)
del email_analysis.db
python main.py
```

### Problème 3 : Pricing Ne S'Affiche Pas

**Symptôme** : Frontend affiche "À calculer"

**Cause** :
1. `PRICING_ENGINE_ENABLED=false` dans `.env`
2. Pas de prix fournisseur dans `supplier_tariffs.db`
3. Erreur Phase 5 pricing

**Debug** :
```bash
# Vérifier .env
cat .env | grep PRICING_ENGINE_ENABLED

# Tester pricing isolé
python test_pricing_with_real_product.py

# Vérifier logs backend pendant analyse
```

---

## Performance Attendue

| Opération | Temps Avant | Temps Après |
|-----------|-------------|-------------|
| 1ère analyse | 2-5s | 2-5s (identique) |
| Consultation (cache mémoire) | 2-5s | **< 1ms** ✅ |
| Consultation (DB) | 2-5s | **< 50ms** ✅ |
| Après redémarrage | 2-5s | **< 50ms** ✅ |

**Gain attendu** : **99% de réduction** pour consultations répétées

---

## Conclusion

Si **TOUS les tests passent** :

✅ **Problème résolu** : "À chaque fois que je reviens sur la boite de réception, le programme se relance"

✅ **Comportement correct** :
- Analyse faite **UNE SEULE FOIS**
- Résultat **ENREGISTRÉ** en base SQLite
- Consultations suivantes **INSTANTANÉES**

✅ **Prochaine étape** : Continuer Phase 5 (ProductActionsMenu, EmailList, Webhook)

---

Si **UN SEUL test échoue** :

❌ **Contacter Claude avec** :
1. Logs backend complets (50 dernières lignes)
2. Erreurs console frontend (F12)
3. Résultat commande : `sqlite3 email_analysis.db "SELECT COUNT(*) FROM email_analysis"`
4. Capture d'écran interface

**Commande debug rapide** :
```bash
# Backend
python test_persistance_db.py

# Base données
sqlite3 email_analysis.db "SELECT email_id, analyzed_at FROM email_analysis ORDER BY analyzed_at DESC LIMIT 5"
```
