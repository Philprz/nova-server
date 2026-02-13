# Test Visuel - Pricing Automatique Phase 5

**Date** : 2026-02-13
**Version** : NOVA-SERVER v2.4.0
**Build Frontend** : ✅ Réussi (0 erreurs TypeScript)

---

## 🎯 Objectif du Test

Vérifier que le **pricing automatique (Phase 5)** s'affiche correctement dans l'interface QuoteSummary.

---

## ✅ Modifications Implémentées

### Backend (Python)
1. ✅ `services/email_matcher.py` - Modèle `MatchedProduct` étendu (+10 champs pricing)
2. ✅ `routes/routes_graph.py` - Phase 5 pricing automatique (~110 lignes)
3. ✅ `routes/routes_graph.py` - 3 endpoints actions produits (~220 lignes)
4. ✅ `services/pricing_engine.py` - Cache pricing (TTL 5min)
5. ✅ `services/product_mapping_db.py` - Table `product_exclusions`

### Frontend (TypeScript/React)
6. ✅ `mail-to-biz/src/lib/graphApi.ts` - Interface `ProductMatch` étendue
7. ✅ `mail-to-biz/src/components/QuoteSummary.tsx` - Affichage pricing automatique

**Total Backend** : ~350 lignes
**Total Frontend** : ~80 lignes
**Build** : ✅ Sans erreurs

---

## 🚀 Comment Tester

### Étape 1 : Démarrer le serveur (si pas déjà fait)

```bash
cd C:\Users\PPZ\NOVA-SERVER
python main.py
```

Le serveur devrait démarrer sur `http://localhost:8001`

### Étape 2 : Accéder à l'interface Mail-to-Biz

Ouvrir le navigateur :
```
http://localhost:8001/
```

Ou si le tunnel Cloudflare est actif :
```
https://<votre-url-cloudflare>/
```

### Étape 3 : Tester le Workflow

#### 3.1 Connexion Microsoft 365
- Se connecter avec les credentials Office 365
- Autoriser l'accès à la boîte mail

#### 3.2 Analyser un Email de Devis
- Sélectionner un email contenant une demande de devis
- Cliquer sur le bouton **"Traiter"**
- ⏱️ Attendre l'analyse (2-5 secondes)

#### 3.3 Vérifier la Synthèse du Devis

**Ce que vous DEVRIEZ voir** si le pricing fonctionne :

1. **Colonne "Prix estimé"** (dans le tableau des articles) :
   ```
   Prix unitaire: XX.XX €
   Badge: [Historique Client] / [Prix Modifié] / [Prix Moyen] / [Nouveau Produit]
   Total: XX.XX €
   [Validation requise] (si CAS 2 ou 4)
   ```

2. **Bloc "Pricing"** (en bas) :
   ```
   Sous-total HT: XX.XX €
   Marge moyenne: XX%
   Total HT: XX.XX €
   ```

**Ce que vous verrez si le pricing N'A PAS fonctionné** :
   ```
   Prix estimé: À calculer
   Sous-total HT: À calculer
   Total HT: À calculer
   ```

---

## 🔍 Points de Vérification

### ✅ Backend
- [ ] Le serveur FastAPI démarre sans erreur
- [ ] Endpoint `/api/graph/emails/{id}/analyze` fonctionne
- [ ] Logs montrent `💰 Calcul pricing pour X produits...`
- [ ] Logs montrent `✓ CAS_X: ITEM_CODE → XX.XX EUR`

### ✅ Frontend
- [ ] Interface se charge sans erreur console
- [ ] Bouton "Traiter" est présent
- [ ] Analyse se lance au clic
- [ ] QuoteSummary s'affiche après analyse

### ✅ Pricing
- [ ] Prix unitaires affichés (pas "À calculer")
- [ ] Badges CAS visibles (CAS_1_HC, CAS_2_HCM, etc.)
- [ ] Totaux calculés dynamiquement
- [ ] Badge "Validation requise" si CAS 2 ou 4

---

## 🐛 Problèmes Potentiels

### Problème 1 : "À calculer" partout

**Cause possible** : Les données de pricing ne remontent pas du backend au frontend

**Solution** :
1. Vérifier les logs backend pendant l'analyse
2. Vérifier que `PRICING_ENGINE_ENABLED=true` dans `.env`
3. Vérifier que les produits ont des prix fournisseurs dans `supplier_tariffs.db`

**Debug** :
```bash
# Tester le pricing directement
python test_pricing_with_real_product.py
```

### Problème 2 : Erreur TypeScript dans la console

**Cause possible** : Type mismatch entre backend et frontend

**Solution** :
1. Ouvrir la console navigateur (F12)
2. Noter l'erreur exacte
3. Vérifier que les champs `unit_price`, `pricing_case`, etc. existent dans les données

### Problème 3 : Badges CAS ne s'affichent pas

**Cause possible** : Champ `pricing_case` manquant ou format incorrect

**Solution** :
1. Inspecter les données dans la console (F12 > Network > analyze)
2. Vérifier le format : `"pricing_case": "CAS_1_HC"`

---

## 📊 Exemple de Données Attendues

Après l'analyse, les `product_matches` devraient ressembler à :

```json
{
  "product_matches": [
    {
      "item_code": "0237154",
      "item_name": "COULOIR 23-7154",
      "quantity": 10,
      "score": 100,
      "match_reason": "Match exact",

      "unit_price": 15.50,
      "line_total": 155.00,
      "pricing_case": "CAS_1_HC",
      "pricing_justification": "Reprise prix dernière vente...",
      "requires_validation": false,
      "supplier_price": 10.00,
      "margin_applied": 55.0,
      "confidence_score": 1.0,
      "alerts": []
    }
  ]
}
```

---

## 📝 Checklist Post-Test

Après le test visuel, noter :

- [ ] **Le pricing s'affiche-t-il ?** (Oui / Non)
- [ ] **Les badges CAS sont-ils corrects ?** (Oui / Non)
- [ ] **Les totaux sont-ils calculés ?** (Oui / Non)
- [ ] **Y a-t-il des erreurs console ?** (Oui / Non / Lesquelles)
- [ ] **Les couleurs/styles sont-ils OK ?** (Oui / Non)

---

## 🎯 Prochaines Étapes (Si le test est OK)

1. ✅ Créer composant `ProductActionsMenu.tsx` (3 actions articles non trouvés)
2. ✅ Modifier `EmailList.tsx` (supprimer bouton "Traiter" + badges statut auto)
3. ✅ Implémenter webhook Microsoft Graph (traitement 100% automatique)
4. ✅ Créer script `register_webhook.py`
5. ✅ Tests end-to-end complets

---

## 🚨 Si Problème Bloquant

**Contacter Claude avec** :
1. Logs backend (copier les 50 dernières lignes)
2. Erreurs console frontend (screenshot ou texte)
3. Capture d'écran de l'interface QuoteSummary
4. Données retournées par `/analyze` (Network tab F12)

**Commande debug rapide** :
```bash
# Backend : Tester pricing isolé
python test_pricing_with_real_product.py

# Frontend : Rebuild si changement
cd mail-to-biz && npm run build && cd .. && cp -r mail-to-biz/dist/* frontend/
```

---

## ✨ Bon Test !

Le pricing automatique devrait fonctionner. Si tout s'affiche correctement, nous pourrons passer aux composants suivants (ProductActionsMenu, EmailList, Webhook).
