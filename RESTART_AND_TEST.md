# Fix Appliqué - Instructions de Redémarrage

## Corrections Appliquées ✅

### 1. Mots-clés "chiffrage" ajoutés
**Fichier:** `services/email_analyzer.py` ligne 35-48
- Ajout de "demande de chiffrage", "demande chiffrage", etc.

### 2. Fix body_content vs body_preview
**Fichier:** `routes/routes_graph.py` ligne 404-416
- Détection explicite si body_content est vide
- Logs pour debug

### 3. Fix timeout pièces jointes (NOUVEAU) 🔥
**Fichier:** `routes/routes_graph.py` ligne 390-430
- **Limite de taille PDF:** 5 MB max
- **Timeout téléchargement:** 30 secondes
- **Timeout parsing:** 30 secondes
- **Comportement:** Skip les PDFs trop gros ou lents, continue l'analyse

**Impact:** L'analyse ne devrait plus timeout. Maximum 60 secondes au lieu de 3+ minutes.

## Actions Requises

### 1. Arrêter le Backend
```bash
# Dans le terminal où tourne le backend
Ctrl+C

# Attendre le message de confirmation
```

### 2. Relancer le Backend
```bash
cd C:\Users\PPZ\NOVA-SERVER
python main.py
```

**Vérifier dans les logs:**
```
NOVA DEMARRE AVEC SUCCES
Uvicorn running on http://0.0.0.0:8001
```

### 3. Tester l'Email MarmaraCam

**Option A: Via Script Python (RECOMMANDÉ)**
```bash
python test_marmaracam_direct.py
```

**Résultat attendu (en moins de 60s):**
```
[OK] EMAIL DETECTE COMME DEVIS!
Le probleme etait le cache. Rafraichissez la page (F5).
```

**Option B: Via l'Interface Web**
1. Rafraîchir la page (F5)
2. Cliquer sur "Demande chiffrage MarmaraCam"
3. Vérifier le statut: doit être "Devis détecté" (badge vert)

### 4. Vérifier les Logs Backend

Après avoir cliqué sur l'email, cherchez dans les logs:

```
[BACKEND] Forcing new analysis for AAMkADI0Mjc0NDZm...
[BACKEND] Using full body_content (XXXX chars)
[BACKEND] PDF xxx.pdf trop gros (X.X MB), skip    ← Si PDF trop gros
[BACKEND] Timeout lors du traitement du PDF xxx   ← Si PDF trop lent
[BACKEND] PDF xxx.pdf extrait avec succès (XXX chars)  ← Si PDF OK
```

## Logs à Surveiller

### ✅ Logs BONS
```
INFO - Forcing new analysis for ...
INFO - Using full body_content (3049 chars)
INFO - PDF skip (trop gros ou timeout)
```

### ❌ Logs MAUVAIS
```
WARNING - using body_preview (255 chars) - may be truncated!
ERROR - Timeout lors du traitement du PDF
```

## Si le Problème Persiste

### Diagnostic 1: Vérifier que le nouveau code est chargé

Dans les logs au démarrage, cherchez la date/heure du démarrage:
```
2026-02-12 16:XX:XX - NOVA DEMARRE AVEC SUCCES
```

Cette date doit être **APRÈS** le moment où vous avez relancé le backend.

### Diagnostic 2: Vérifier les imports

Le fichier `routes/routes_graph.py` doit avoir:
```python
import asyncio  # ligne 7
```

### Diagnostic 3: Vider le cache navigateur

```
Ctrl + Shift + R (hard refresh)
Ou
F12 > Application > Clear storage > Clear site data
```

### Diagnostic 4: Analyser directement via curl

```bash
curl -X POST "http://localhost:8001/api/graph/emails/AAMkADI0Mjc0NDZmLTYyYmUtNGE0NC04YjEzLTM3NDk2NGYwNjFkNwBGAAAAAABJXEqH4KjITaiSBzfaWvvXBwAUuRiIdNuMSoMEzumJldkiAAAAAAEMAAAUuRiIdNuMSoMEzumJldkiAAAQdtcfAAA=/analyze?force=true" \
  -H "Content-Type: application/json" | jq '.is_quote_request'
```

**Résultat attendu:** `true`

## Résumé des Timeouts

| Opération | Timeout Avant | Timeout Après |
|-----------|---------------|---------------|
| Téléchargement PDF | ∞ (pas de limite) | 30s |
| Parsing PDF | ∞ (pas de limite) | 30s |
| Analyse totale | ∞ (timeout client 180s) | ~60s max |

## Prochaines Étapes si OK ✅

1. ✅ Email MarmaraCam détecté comme "Devis"
2. 📋 Vérifier que les autres emails fonctionnent toujours
3. 🧪 Tester avec d'autres emails contenant "chiffrage"
4. 📊 Monitorer les logs pour voir combien de PDFs sont skippés

## Contact / Support

Si après redémarrage l'email n'est toujours pas détecté:

1. Partager les **logs backend complets** (50 dernières lignes)
2. Partager le résultat de `python test_marmaracam_direct.py`
3. Vérifier la version du code avec: `git log --oneline -1`
