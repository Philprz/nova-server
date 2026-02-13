# Fix "Chiffrage" - Instructions de Validation

## Problème Identifié

L'email avec sujet "Demande chiffrage MarmaraCam" est classé comme "Non pertinent" au lieu de "Devis détecté".

## Cause Racine

**Double cache** qui empêche la réanalyse:
1. **Cache frontend** (React - `useEmails.ts`)
2. **Cache backend** (FastAPI - `routes_graph.py`)

Même si le code a été corrigé, les caches contiennent encore l'ancienne analyse.

## Correction Appliquée ✅

**Fichier modifié:** `services/email_analyzer.py` (lignes 35-48)

**Mots-clés ajoutés dans `QUOTE_KEYWORDS_BODY`:**
- `'demande de chiffrage'`
- `'demande chiffrage'`
- `'veuillez nous faire un chiffrage'`
- `'pouvez-vous chiffrer'`
- `'merci de chiffrer'`

**Note:** Le mot `'chiffrage'` était déjà présent dans `QUOTE_KEYWORDS_SUBJECT`.

## Étapes de Validation

### Étape 1: Redémarrer le Backend (OBLIGATOIRE)

```bash
# Arrêter le backend actuel
Ctrl + C

# Relancer le backend
python main.py
```

**Pourquoi?** Pour charger le code corrigé et vider le cache backend.

### Étape 2: Vider le Cache Frontend

**Option A - Rafraîchir la page:**
- Appuyer sur `F5` dans le navigateur
- Ou `Ctrl + F5` (hard refresh)

**Option B - Vider le localStorage:**
- Ouvrir DevTools (F12)
- Console → `localStorage.clear()`
- Rafraîchir la page

### Étape 3: Tester avec l'Email Réel

#### Option 3A - Via l'Interface Web (après F5)

1. Aller sur http://localhost:5173 (ou votre URL frontend)
2. Cliquer sur l'email "Demande chiffrage MarmaraCam"
3. Vérifier la classification:
   - **Attendu:** Badge vert "Devis détecté" ou "QUOTE_REQUEST"
   - **Si Non pertinent:** Passer à l'Option 3B

#### Option 3B - Via Script de Test Direct

```bash
# 1. Récupérer l'ID de l'email
curl http://localhost:8001/api/graph/emails | jq '.[] | select(.subject | contains("chiffrage")) | .id'

# 2. Copier l'ID trouvé

# 3. Éditer test_chiffrage_api_real.py
# Remplacer EMAIL_ID = "REMPLACER_PAR_VOTRE_EMAIL_ID"
# par EMAIL_ID = "votre-id-copié"

# 4. Lancer le test
python test_chiffrage_api_real.py
```

**Résultat attendu:**
```
[OK] Email correctement detecte comme QUOTE_REQUEST
Le fix fonctionne! Le mot 'chiffrage' est maintenant reconnu.
```

### Étape 4: Test Unitaire (Déjà Validé ✅)

```bash
python test_chiffrage_detection.py
```

**Résultat obtenu:**
```
Score total: 55 (seuil: 15)
Likely quote: True
Confidence: high
Regles matchees:
  [+] Subject contains 'chiffrage'
  [+] Body contains quote phrase

[OK] PRE-FILTRAGE: Email correctement classe comme 'demande de devis'
[OK] ANALYSE LLM: Email correctement classe comme 'QUOTE_REQUEST'
```

## Vérification Backend Redémarré

```bash
python clear_analysis_cache.py
```

Ce script vérifie que le backend est bien accessible et affiche son uptime.
- Si uptime > 1 minute → Le backend n'a pas été redémarré récemment
- **Action:** Redémarrer le backend (Étape 1)

## Logs à Vérifier

Lors de l'analyse d'un email avec "chiffrage", vous devriez voir dans les logs backend:

```
INFO:services.email_analyzer:EmailAnalyzer instance created
INFO:routes.routes_graph:Forcing new analysis for {message_id}
```

Et le résultat JSON devrait contenir:
```json
{
  "classification": "QUOTE_REQUEST",
  "is_quote_request": true,
  "quick_filter_passed": true,
  "confidence": "high",
  "reasoning": "...demande de chiffrage..."
}
```

## Si le Problème Persiste

### Vérification 1: Code Bien Modifié

```bash
# Vérifier que les nouveaux mots-clés sont présents
grep -A 10 "QUOTE_KEYWORDS_BODY" services/email_analyzer.py
```

Vous devriez voir:
```python
QUOTE_KEYWORDS_BODY = [
    ...
    'demande de chiffrage', 'demande chiffrage',
    ...
    'veuillez nous faire un chiffrage',
    'pouvez-vous chiffrer', 'merci de chiffrer'
]
```

### Vérification 2: Backend Utilise le Bon Code

```bash
# Dans une console Python avec le backend lancé
import services.email_analyzer as ea
print(ea.QUOTE_KEYWORDS_BODY)
```

Vous devriez voir les nouveaux mots-clés dans la liste.

### Vérification 3: Contenu Exact de l'Email

```bash
# Récupérer le sujet et corps exact
curl http://localhost:8001/api/graph/emails/{EMAIL_ID} | jq '.subject, .body_preview'
```

Vérifiez que:
- Le mot "chiffrage" est bien présent (sans accent, sans majuscule bizarre)
- Le format est bien "Demande chiffrage" ou "demande de chiffrage"

## Amélioration Future (Optionnel)

Pour éviter ce problème de cache à l'avenir, on pourrait:

1. **Ajouter un bouton "Réanalyser" dans l'interface:**
   - Appelle l'API avec `force=true`
   - Utile pour forcer une réanalyse sans F5

2. **Invalider automatiquement le cache frontend:**
   - Ajouter un timestamp de version du backend
   - Si version change, vider le cache automatiquement

3. **Réduire la durée de vie du cache:**
   - Cache backend: 1 heure au lieu de permanent
   - Cache frontend: 30 minutes au lieu de permanent

## Résumé Court

```bash
# 1. Redémarrer backend (OBLIGATOIRE)
Ctrl+C puis python main.py

# 2. Rafraîchir frontend
F5 dans le navigateur

# 3. Tester
python test_chiffrage_detection.py  # Test unitaire ✅
python test_chiffrage_api_real.py    # Test API avec email réel
```

**Résultat attendu:** Email "Demande chiffrage MarmaraCam" classé comme **QUOTE_REQUEST** ✅
