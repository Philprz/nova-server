# Diagnostic Email "Demande chiffrage MarmaraCam"

## Situation

Email classé comme "Non pertinent" alors qu'il devrait être "Devis détecté".

- **Sujet:** Demande chiffrage MarmaraCam
- **Corps:** "Veuillez trouver ci-joint la demande de chiffrage..."
- **Expéditeur:** Philippe PEREZ (transféré de msezen@marmaracam.com.tr)

## Tests Effectués ✅

### Test 1: Code de détection avec texte exact
```bash
python test_marmaracam_exact.py
```

**Résultat:** ✅ DÉTECTÉ
- Score: 55 (seuil: 15)
- Classification: QUOTE_REQUEST
- Confidence: high

### Test 2: Simulation body tronqué
```bash
python test_truncated_preview.py
```

**Résultat:** ✅ DÉTECTÉ même avec preview tronqué
- Score: 55
- Raison: "chiffrage" dans le SUJET suffit

### Test 3: Mots-clés ajoutés dans email_analyzer.py

**Résultat:** ✅ PRÉSENTS
- `QUOTE_KEYWORDS_SUBJECT`: contient 'chiffrage'
- `QUOTE_KEYWORDS_BODY`: contient 'demande de chiffrage', 'demande chiffrage', etc.

## Conclusion des Tests

**Le code fonctionne PARFAITEMENT.** Le problème est donc:

### Hypothèse #1: Cache (TRÈS PROBABLE) 🔴

L'ancienne analyse est toujours en cache malgré le redémarrage.

**Emplacements du cache:**
1. **Cache backend** (`routes_graph.py` ligne 357): dictionnaire `_analysis_cache` en mémoire
2. **Cache frontend** (`useEmails.ts` ligne 150): Map JavaScript `analysisCache`

**Solution:**
```bash
# 1. Arrêter complètement le backend
Ctrl+C (attendre confirmation)

# 2. Vérifier qu'il est bien arrêté
# Pas de processus Python en cours

# 3. Relancer
python main.py

# 4. Dans le navigateur
F5 (ou Ctrl+Shift+R pour hard refresh)

# 5. Vérifier les logs backend
# Chercher: "Forcing new analysis for {id}"
```

### Hypothèse #2: Sujet/Corps réel différent ⚠️

Le sujet ou le corps de l'email réel est peut-être différent de ce que vous voyez dans l'interface.

**Test avec API directe:**
```bash
# 1. Trouver l'ID de l'email
curl http://localhost:8001/api/graph/emails | jq '.[] | select(.subject | contains("MarmaraCam"))'

# 2. Copier l'ID

# 3. Éditer debug_marmaracam_real_api.py
#    Remplacer EMAIL_ID par l'ID réel

# 4. Lancer
python debug_marmaracam_real_api.py
```

Ce script montrera:
- Le sujet EXACT
- Le body EXACT (preview ET complet)
- Si "chiffrage" est présent
- Le score de classification

### Hypothèse #3: Interface affiche une ancienne version 🔄

L'interface pourrait afficher une ancienne analyse même si le backend a reclassifié l'email.

**Test:**
```bash
# Appeler directement l'API avec force=true
curl -X POST "http://localhost:8001/api/graph/emails/{EMAIL_ID}/analyze?force=true"

# Comparer avec ce que l'interface affiche
```

### Hypothèse #4: Problème de permissions/récupération email 🔐

Microsoft Graph ne retourne peut-être pas le sujet complet ou le body.

**Vérification dans les logs:**

Après le fix appliqué ligne 405-412 de `routes_graph.py`, les logs afficheront:
- `"Using full body_content (XXX chars)"` → Body complet récupéré ✅
- `"using body_preview (XXX chars) - may be truncated!"` → Preview tronqué ⚠️

Si vous voyez le warning, c'est que Microsoft Graph ne retourne pas le `body_content`.

## Correctifs Appliqués

### 1. Mots-clés enrichis ✅

**Fichier:** `services/email_analyzer.py` ligne 35-48

**Ajouts:**
- `'demande de chiffrage'`
- `'demande chiffrage'`
- `'veuillez nous faire un chiffrage'`
- `'pouvez-vous chiffrer'`
- `'merci de chiffrer'`

### 2. Fix body_content vs body_preview ✅

**Fichier:** `routes/routes_graph.py` ligne 404-416

**Avant:**
```python
body_text = email.body_content or email.body_preview
```

**Après:**
```python
if email.body_content and len(email.body_content.strip()) > 0:
    body_text = email.body_content
    logger.info(f"Using full body_content ({len(body_text)} chars)")
else:
    body_text = email.body_preview
    logger.warning(f"body_content empty/missing, using body_preview ({len(body_text)} chars) - may be truncated!")
```

**Avantage:** Détecte explicitement si body_content est vide et log ce qui est utilisé.

## Actions Requises (PAR ORDRE DE PRIORITÉ)

### Action 1: Redémarrage complet 🔴 CRITIQUE

```bash
# Backend
Ctrl+C (arrêt complet)
python main.py

# Frontend
F5 dans le navigateur
```

### Action 2: Vérifier les logs backend 📋

Cherchez ces lignes quand vous cliquez sur l'email MarmaraCam:

```
INFO:routes.routes_graph:Forcing new analysis for {message_id}
INFO:routes.routes_graph:Using full body_content (XXX chars)
INFO:services.email_analyzer:EmailAnalyzer instance created
```

Si vous voyez:
- `"Returning cached analysis"` → Cache pas vidé, redémarrer à nouveau
- `"using body_preview (XXX chars)"` → Problème récupération body, passer à Action 3

### Action 3: Test avec email réel via API 🔍

```bash
# Éditer debug_marmaracam_real_api.py avec l'EMAIL_ID réel
python debug_marmaracam_real_api.py
```

Ce script dira EXACTEMENT pourquoi l'email n'est pas détecté.

### Action 4: Forcer l'analyse via curl 🚀

```bash
# Remplacer {EMAIL_ID} par l'ID réel
curl -X POST "http://localhost:8001/api/graph/emails/{EMAIL_ID}/analyze?force=true"
```

Vérifiez la réponse JSON:
```json
{
  "classification": "QUOTE_REQUEST",  // Doit être QUOTE_REQUEST
  "is_quote_request": true,           // Doit être true
  "confidence": "high",                // high, medium ou low
  "quick_filter_passed": true         // Doit être true
}
```

Si `is_quote_request: false`, regardez le `reasoning` pour comprendre pourquoi.

## Si le Problème Persiste après TOUT

Si après avoir:
1. ✅ Redémarré backend ET frontend
2. ✅ Vérifié les logs
3. ✅ Testé avec l'API directe avec force=true
4. ✅ Confirmé que le code contient les mots-clés

L'email est TOUJOURS classé "Non pertinent", alors:

### Hypothèse finale: Autre filtre dans le code

Il existe peut-être un autre endroit dans le code qui filtre/rejette cet email.

**Recherche:**
```bash
# Chercher tous les endroits où on modifie is_quote_request
grep -r "is_quote_request.*=" --include="*.py"

# Chercher tous les filtres de classification
grep -r "classification.*=" --include="*.py"
```

Ou le problème est dans le **frontend** qui affiche une classification différente de celle du backend.

**Vérification:**
```javascript
// Dans DevTools > Network
// Cliquer sur l'email
// Chercher la requête: /api/graph/emails/{id}/analyze
// Regarder la Response (JSON)
// Comparer avec ce que l'interface affiche
```

## Résumé des Scripts de Test

| Script | Utilité |
|--------|---------|
| `test_chiffrage_detection.py` | Test unitaire avec texte simulé ✅ |
| `test_marmaracam_exact.py` | Test avec le texte exact fourni ✅ |
| `test_truncated_preview.py` | Test simulation preview tronqué ✅ |
| `debug_marmaracam_real_api.py` | Récupère l'email RÉEL via API 🔍 |
| `test_chiffrage_api_real.py` | Test API avec force=true 🚀 |
| `clear_analysis_cache.py` | Vérification cache/uptime 📊 |

## Contact / Support

Si le problème persiste après toutes ces étapes, fournissez:

1. **Logs backend** (les 50 dernières lignes lors du clic sur l'email)
2. **Résultat de** `debug_marmaracam_real_api.py`
3. **Réponse JSON** de `/analyze?force=true`
4. **Screenshot** de l'interface montrant le statut "Non pertinent"

Cela permettra d'identifier précisément le problème.
