# 🔧 Guide de Correction Frontend - Mail-to-Biz

**Date:** 2026-02-13
**Objectif:** Afficher les bonnes données dans l'interface (CardCode C0249, 34 produits)

---

## ✅ Problème Identifié

Le frontend **fait sa propre extraction locale** via `preSapNormalizer.ts` au lieu d'utiliser les données matchées du backend.

**Résultat actuel:**
- CardCode: `null` (au lieu de `C0249`)
- Produits: 6 (au lieu de 34)
- Faux positifs non filtrés

---

## 🎯 Solution Implémentée

### Nouveau Endpoint Backend

**URL:** `GET /api/export-v2/pre-sap-quote/{email_id}`

**Avantages:**
- ✅ Réutilise l'analyse existante (pas de retraitement)
- ✅ Retourne directement le format pre-sap-quote
- ✅ Inclut les données matchées du backend (client_matches, product_matches)
- ✅ Faux positifs déjà filtrés

**Format retourné:**
```json
{
  "sap_document_type": "SalesQuotation",
  "business_partner": {
    "CardCode": "C0249",
    "CardName": "MARMARA CAM SANAYI VE TICARET AS",
    "ContactEmail": "msezen@marmaracam.com.tr",
    "ToBeCreated": false
  },
  "document_lines": [
    {
      "ItemCode": "C391-14-LM",
      "ItemDescription": "C391-14-LM",
      "Quantity": 60,
      "RequestedDeliveryDate": null,
      "ToBeCreated": false
    }
    // ... 34 produits au total
  ],
  "meta": {
    "source": "office365",
    "email_id": "...",
    "confidence_level": "high",
    "manual_validation_required": false,
    "validated": false,
    "client_score": 97,
    "product_count": 34,
    "false_positives_filtered": true,
    "classification": "QUOTE_REQUEST",
    "reasoning": "..."
  }
}
```

---

## 📋 Étapes de Correction

### 1. Redémarrer le Backend

```bash
# Arrêter le backend actuel (Ctrl+C)
# Puis relancer:
python main.py
# OU
uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

### 2. Tester le Nouvel Endpoint

```bash
python test_export_v2.py
```

**Résultat attendu:**
```
✅ CardCode correct: C0249 (MARMARA CAM)
✅ Nombre de produits correct: 34
✅ Classification correcte: QUOTE_REQUEST
✅ Faux positifs filtrés
🎯 TOUS LES TESTS PASSENT - READY FOR DEMO!
```

### 3. Modifier le Frontend (mail-to-biz)

**Fichier à modifier:** `mail-to-biz/src/lib/preSapNormalizer.ts`

**Option A - Modification Rapide (Recommandée pour la démo):**

Ajouter une nouvelle fonction qui appelle directement l'endpoint v2:

```typescript
// Nouvelle fonction qui utilise le backend v2
export async function fetchPreSapFromBackend(emailId: string): Promise<PreSapDocument> {
  const response = await fetch(
    `http://localhost:8001/api/export-v2/pre-sap-quote/${emailId}`
  );

  if (!response.ok) {
    throw new Error(`Export failed: ${response.statusText}`);
  }

  const backendData = await response.json();

  // Convertir snake_case → camelCase pour le frontend
  return {
    sapDocumentType: backendData.sap_document_type,
    businessPartner: {
      CardCode: backendData.business_partner.CardCode,
      CardName: backendData.business_partner.CardName,
      ContactEmail: backendData.business_partner.ContactEmail,
      ToBeCreated: backendData.business_partner.ToBeCreated,
    },
    documentLines: backendData.document_lines.map((line: any, index: number) => ({
      LineNum: index + 1,
      ItemCode: line.ItemCode,
      ItemDescription: line.ItemDescription,
      Quantity: line.Quantity,
      UnitOfMeasure: 'pcs',
      RequestedDeliveryDate: line.RequestedDeliveryDate,
      ToBeCreated: line.ToBeCreated,
      SourceType: 'email' as const,
    })),
    requestedDeliveryDate: null,
    deliveryLeadTimeDays: null,
    meta: {
      source: 'office365',
      emailId: backendData.meta.email_id,
      receivedDate: new Date().toISOString(),
      confidenceLevel: backendData.meta.confidence_level,
      manualValidationRequired: backendData.meta.manual_validation_required,
      detectionRules: [backendData.meta.reasoning],
      sourceConflicts: [],
      validationStatus: 'pending',
      validatedAt: null,
      validatedBy: null,
    },
  };
}
```

**Option B - Utiliser la Fonction Existante (Plus d'intégration):**

Modifier la fonction `normalizeFromBackendAnalysis()` existante pour utiliser directement les données du endpoint v2:

```typescript
// Dans le composant qui affiche l'email
const analysis = await fetch(`/api/export-v2/pre-sap-quote/${emailId}`).then(r => r.json());
// Pas besoin de normalizeFromBackendAnalysis, on a déjà le bon format!
```

---

## 🧪 Tests Finaux

Avant la démo, vérifier:

1. **Backend démarré:** `http://localhost:8001/health` → ✅ OK
2. **Endpoint v2 fonctionne:** `python test_export_v2.py` → ✅ PASS
3. **Interface affiche les bonnes données:**
   - CardCode: `C0249` ✅
   - Produits: `34` ✅
   - Classification: `Devis détecté` ✅

---

## ⏰ Timeline Recommandée

**Temps restant:** 1h15

1. **0-5 min:** Redémarrer backend + tester endpoint v2
2. **5-20 min:** Modifier frontend (Option A recommandée)
3. **20-30 min:** Tester interface complète
4. **30-60 min:** Répéter scénario démo 2-3 fois
5. **60-75 min:** Buffer pour imprévus

---

## 📞 Vérification Rapide

```bash
# 1. Backend OK ?
curl http://localhost:8001/health

# 2. Endpoint v2 OK ?
python test_export_v2.py

# 3. Frontend accessible ?
curl http://localhost:8082/mail-to-biz
```

---

## 🎯 Résumé

**Avant:**
```
Frontend → Extraction locale → Données incorrectes
```

**Après:**
```
Frontend → GET /api/export-v2/pre-sap-quote/{id} → Données correctes du backend
```

**Avantage clé:** Le backend a déjà fait tout le travail (matching, filtrage), le frontend n'a qu'à afficher !

---

**Prêt pour la démo dans 1h15 ! 🚀**
