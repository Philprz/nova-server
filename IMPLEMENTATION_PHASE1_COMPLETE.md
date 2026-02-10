# 🎯 Phase 1 - Implémentation Complète

## ✅ Composants Implémentés

### 1. Moteur de Pricing Intelligent RONDOT-SAS

**Fichiers créés** :
- ✅ `services/pricing_models.py` (260 lignes) - Modèles Pydantic complets
- ✅ `services/pricing_engine.py` (300 lignes) - Logique CAS 1/2/3/4
- ✅ `services/sap_history_service.py` (250 lignes) - Accès historiques SAP
- ✅ `services/pricing_audit_db.py` (280 lignes) - Base de données audit

**Fichiers modifiés** :
- ✅ `routes/routes_sap_business.py` (lignes 382-470) - Intégration pricing engine

#### Cas de Pricing Implémentés

| CAS | Condition | Décision | Validation | Traçabilité |
|-----|-----------|----------|------------|-------------|
| **CAS 1 (HC)** | Article déjà vendu à CE client + variation prix fournisseur < 5% | Reprendre prix dernière vente | ❌ Non requise | Date vente, doc num, variation % |
| **CAS 2 (HCM)** | Article déjà vendu à CE client + variation prix fournisseur ≥ 5% | Recalculer avec marge 45% | ✅ **REQUISE** | Ancien vs nouveau prix, écart, justification, alerte commerciale |
| **CAS 3 (HA)** | Jamais vendu à CE client, mais vendu à AUTRES | Prix moyen pondéré (récence + quantité) | ❌ Non requise (sauf < 3 ventes) | Clients référence, prix moyen, nombre ventes |
| **CAS 4 (NP)** | Jamais vendu nulle part | Prix fournisseur + marge 45% | ✅ **REQUISE** | Aucun historique, première vente |

### 2. Service Microsoft Graph (Emails Office 365)

**Fichiers existants** :
- ✅ `services/graph_service.py` (353 lignes) - Service Graph complet avec cache token
- ✅ `routes/routes_graph.py` (436 lignes) - Endpoints API complets

**Fonctionnalités disponibles** :
- Récupération emails avec pagination
- Analyse IA à la demande
- Extraction automatique PDFs
- Cache des analyses (évite appels IA redondants)
- Gestion pièces jointes (<4MB et >4MB)
- Marquage emails comme lus

### 3. Calculateur de Transport (Version Basique)

**Fichier créé** :
- ✅ `services/transport_calculator.py` (150 lignes)

**Logique Phase 1** :
- Utilise `transport_cost` depuis `supplier_products` (base existante)
- Calcul : `poids_total = poids_unitaire × quantité`
- Coût : `coût_total = transport_cost × quantité`
- Pas d'API transporteurs (prévu Phase 2)

---

## 🔍 Tests End-to-End à Effectuer

### Scénario 1 : CAS 1 - Client Fidèle (Prix Stable)

**Contexte** :
- Client existant dans SAP (ex: `C00001`)
- Article déjà vendu à ce client à 150,00 EUR
- Prix fournisseur actuel : 105,00 EUR (variation < 5% depuis dernier achat)

**Test** :
```bash
POST /api/sap-business/process-email-to-quote
{
  "email_data": {
    "client_name": "ENTREPRISE CLIENT FIDELE",
    "client_email": "contact@client-fidele.fr",
    "products": [
      {
        "description": "Article déjà acheté",
        "item_code": "ITEM001",
        "quantity": 10
      }
    ]
  }
}
```

**Résultat attendu** :
```json
{
  "pricing_decisions": [
    {
      "case_type": "CAS_1_HC",
      "calculated_price": 150.00,
      "justification": "Reprise prix dernière vente (150.00 EUR) du 2025-11-15 (Devis 12345). Variation prix fournisseur : +2.50% (stable).",
      "requires_validation": false,
      "confidence_score": 1.0
    }
  ],
  "quote_created": true,
  "doc_num": 67890
}
```

**Points de vérification** :
- ✅ Prix repris identique à la dernière vente
- ✅ Pas de validation commerciale requise
- ✅ Justification complète avec référence document
- ✅ Décision sauvegardée dans `pricing_decisions` table
- ✅ `confidence_score` = 1.0

### Scénario 2 : CAS 2 - Variation Prix Fournisseur (Alerte)

**Contexte** :
- Client existant
- Article déjà vendu à 150,00 EUR
- Prix fournisseur actuel : 120,00 EUR (**+14% depuis dernier achat**)

**Test** :
```bash
POST /api/sap-business/process-email-to-quote
{
  "email_data": {
    "client_name": "ENTREPRISE CLIENT FIDELE",
    "products": [
      {
        "item_code": "ITEM002",
        "quantity": 5
      }
    ]
  }
}
```

**Résultat attendu** :
```json
{
  "pricing_decisions": [
    {
      "case_type": "CAS_2_HCM",
      "calculated_price": 174.00,  // 120 × 1.45
      "justification": "Prix recalculé (174.00 EUR) avec marge 45%. Ancien prix vente : 150.00 EUR. Écart : +24.00 EUR (+16.00%). Variation prix fournisseur : +14.00% (instable).",
      "requires_validation": true,
      "validation_reason": "Variation prix fournisseur importante (+14.00%)",
      "alerts": [
        "⚠ ALERTE COMMERCIALE : Variation prix fournisseur +14.00%",
        "Impact prix vente : +24.00 EUR"
      ],
      "confidence_score": 0.9
    }
  ],
  "requires_commercial_validation": true
}
```

**Points de vérification** :
- ✅ Nouveau prix calculé avec marge 45%
- ✅ **Validation commerciale OBLIGATOIRE**
- ✅ Alertes générées avec écart détaillé
- ✅ Référence à l'ancien prix
- ✅ Devis en attente validation (vérifier workflow)

### Scénario 3 : CAS 3 - Nouveau Client, Article Connu

**Contexte** :
- Client nouveau (non existant dans SAP)
- Article déjà vendu à 3 autres clients : 155 EUR, 160 EUR, 158 EUR
- Prix fournisseur actuel : 110 EUR

**Test** :
```bash
POST /api/sap-business/process-email-to-quote
{
  "email_data": {
    "client_name": "NOUVELLE ENTREPRISE SAS",
    "client_email": "contact@nouvelle-entreprise.fr",
    "siret": "12345678901234",
    "products": [
      {
        "item_code": "ITEM003",
        "quantity": 20
      }
    ]
  }
}
```

**Résultat attendu** :
```json
{
  "client_created": true,
  "pricing_decisions": [
    {
      "case_type": "CAS_3_HA",
      "calculated_price": 157.50,  // Prix moyen pondéré
      "average_price_others": 157.50,
      "reference_sales_count": 3,
      "justification": "Prix moyen pondéré : 157.50 EUR (basé sur 3 ventes à autres clients). Clients référence : C00012, C00045, C00078. Prix fournisseur actuel : 110.00 EUR.",
      "requires_validation": false,
      "confidence_score": 0.85
    }
  ]
}
```

**Points de vérification** :
- ✅ Client créé automatiquement avec enrichissement TVA (INSEE/Pappers)
- ✅ Prix basé sur historique autres clients
- ✅ Liste des clients référence fournie
- ✅ Pas de validation requise (3 ventes > seuil)
- ✅ Si < 3 ventes → alerte et éventuelle validation

### Scénario 4 : CAS 4 - Nouveau Produit (Jamais Vendu)

**Contexte** :
- Article jamais vendu à personne
- Prix fournisseur : 200,00 EUR
- Aucun historique disponible

**Test** :
```bash
POST /api/sap-business/process-email-to-quote
{
  "email_data": {
    "products": [
      {
        "item_code": "ITEM_NOUVEAU",
        "description": "Produit jamais commandé",
        "quantity": 15
      }
    ]
  }
}
```

**Résultat attendu** :
```json
{
  "pricing_decisions": [
    {
      "case_type": "CAS_4_NP",
      "calculated_price": 290.00,  // 200 × 1.45
      "supplier_price": 200.00,
      "margin_applied": 45.0,
      "justification": "Nouveau produit sans historique. Prix calculé : 290.00 EUR (prix fournisseur 200.00 EUR + marge 45%). VALIDATION COMMERCIALE REQUISE.",
      "requires_validation": true,
      "validation_reason": "Nouveau produit sans historique de vente",
      "alerts": [
        "⚠ NOUVEAU PRODUIT : Aucun historique de vente disponible",
        "Validation commerciale OBLIGATOIRE avant création devis"
      ],
      "confidence_score": 0.7
    }
  ],
  "requires_commercial_validation": true
}
```

**Points de vérification** :
- ✅ Prix = prix fournisseur + marge 45%
- ✅ **Validation commerciale OBLIGATOIRE**
- ✅ Alertes spécifiques nouveau produit
- ✅ Confidence score plus faible (0.7)
- ✅ Création article SAP si non existant

### Scénario 5 : Transport Intégré

**Test avec transport** :
```bash
POST /api/sap-business/process-email-to-quote
{
  "email_data": {
    "products": [
      {
        "item_code": "ITEM001",
        "quantity": 50
      }
    ],
    "delivery_requirement": "Livraison rapide"
  }
}
```

**Résultat attendu** :
```json
{
  "pricing_decisions": [...],
  "transport_info": {
    "total_cost": 125.50,
    "total_weight_kg": 75.0,
    "max_delivery_days": 5,
    "carrier": "Standard"
  },
  "quote_total_with_transport": 8125.50
}
```

**Points de vérification** :
- ✅ Poids total calculé (poids unitaire × quantité totale)
- ✅ Coût transport ajouté au total devis
- ✅ Délai livraison affiché
- ✅ Transporteur indiqué

---

## ⚠️ Points Critiques à Vérifier

### 1. Accès SAP aux Historiques

**Endpoints SAP requis** (à tester impérativement) :

#### Factures Ventes
```bash
GET https://[SAP_HOST]/b1s/v1/Invoices
?$filter=CardCode eq 'C00001' and DocDate ge '2024-01-01'
&$expand=DocumentLines
&$orderby=DocDate desc
&$top=50
```

**Permissions requises** :
- ✅ Lecture `/Invoices`
- ✅ Filtre OData : `$filter`, `$expand`, `$orderby`
- ✅ Expansion des lignes de document

#### Factures Achats
```bash
GET https://[SAP_HOST]/b1s/v1/PurchaseInvoices
?$filter=DocDate ge '2024-07-01'
&$expand=DocumentLines
&$orderby=DocDate desc
&$top=20
```

**Permissions requises** :
- ✅ Lecture `/PurchaseInvoices`
- ✅ Accès historique achats fournisseurs

### 2. Variables d'Environnement (.env)

**Microsoft Graph** :
```bash
MS_TENANT_ID=***
MS_CLIENT_ID=***
MS_CLIENT_SECRET=***
MS_MAILBOX_ADDRESS=devis@rondot-sas.fr
```

**SAP Business One** :
```bash
SAP_HOST=https://your-sap-server.com:50000
SAP_COMPANY_DB=RONDOT_SAS
SAP_USER=***
SAP_PASSWORD=***
```

**Pricing Engine** :
```bash
PRICING_ENGINE_ENABLED=true
PRICING_DEFAULT_MARGIN=45.0
PRICING_STABILITY_THRESHOLD=5.0
PRICING_LOOKBACK_DAYS=365
PRICING_REQUIRE_VALIDATION_CAS_4=true
```

### 3. Base de Données SQLite

**Vérifier tables créées** :
```bash
sqlite3 data/supplier_tariffs.db
```

```sql
-- Vérifier table pricing_decisions
SELECT COUNT(*) FROM pricing_decisions;

-- Vérifier table pricing_statistics
SELECT * FROM pricing_statistics;

-- Vérifier index
.indexes pricing_decisions
```

**Tables attendues** :
- ✅ `pricing_decisions` (décisions pricing)
- ✅ `pricing_statistics` (statistiques quotidiennes)
- ✅ Index sur `item_code`, `card_code`, `case_type`, `created_at`, `requires_validation`

### 4. Tests de Connexion

**Test Microsoft Graph** :
```bash
GET /api/graph/test-connection
```

**Résultat attendu** :
```json
{
  "success": true,
  "step": "complete",
  "details": {
    "tenantId": true,
    "clientId": true,
    "clientSecret": true,
    "mailboxAddress": true,
    "tokenAcquired": true,
    "mailboxAccessible": true
  },
  "mailboxInfo": {
    "displayName": "Devis RONDOT",
    "mail": "devis@rondot-sas.fr"
  }
}
```

**Test SAP** :
```bash
GET /api/sap-business/test-connection
```

---

## 📊 Traçabilité et Audit

### Consulter les Décisions Pricing

**Endpoint à créer (optionnel)** :
```bash
GET /api/pricing/decisions?case_type=CAS_2_HCM&limit=20
GET /api/pricing/decisions/pending-validations
GET /api/pricing/statistics?days=30
```

**Requêtes SQL directes** :
```sql
-- Toutes les décisions CAS 2 (avec alerte)
SELECT
    item_code,
    card_code,
    calculated_price,
    justification,
    alerts_json,
    created_at
FROM pricing_decisions
WHERE case_type = 'CAS_2_HCM'
ORDER BY created_at DESC
LIMIT 20;

-- Décisions en attente validation
SELECT
    decision_id,
    item_code,
    card_code,
    case_type,
    validation_reason,
    calculated_price,
    created_at
FROM pricing_decisions
WHERE requires_validation = 1
AND validated_at IS NULL
ORDER BY created_at DESC;

-- Statistiques par CAS
SELECT
    case_type,
    COUNT(*) as count,
    AVG(margin_applied) as avg_margin,
    AVG(confidence_score) as avg_confidence
FROM pricing_decisions
WHERE DATE(created_at) >= DATE('now', '-7 days')
GROUP BY case_type;
```

### Logs Applicatifs

**Vérifier logs détaillés** :
```bash
# Logs pricing engine
grep "Pricing CAS" logs/app.log | tail -50

# Logs alertes commerciales
grep "ALERTE COMMERCIALE" logs/app.log

# Logs transport
grep "Transport calculé" logs/app.log
```

---

## 🚀 Prochaines Étapes (Phase 2 & 3)

### Phase 2 : Enrichissement (Après validation Phase 1)

**Composants à ajouter** :
- 🔄 Service de taux de change (API externe)
- 🔄 Gestion remises fournisseurs (table `supplier_discounts`)
- 🔄 Transport optimisé avec API transporteurs (DHL, UPS, Chronopost, Geodis)
- 🔄 Dashboard métriques temps réel (React)
- 🔄 Comparaison transporteurs en temps réel

**Estimation** : ~850 lignes de code

### Phase 3 : Workflow Validation (Final)

**Composants à ajouter** :
- 🔄 Service de validation de devis (`quote_validator.py`)
- 🔄 Workflow états de devis (draft → pending → validated → sent)
- 🔄 Interface validation commerciale (React)
- 🔄 Ajustements prix manuels avec traçabilité

**Estimation** : ~950 lignes de code

---

## 📝 Métriques de Succès Phase 1

**Objectifs à atteindre** :
- ✅ 100% emails traités automatiquement (classification)
- ✅ 90% clients identifiés/créés automatiquement
- ✅ 85% produits identifiés/créés automatiquement
- ✅ 100% devis avec pricing intelligent (CAS 1/2/3/4)
- ✅ Traçabilité complète de chaque décision
- ✅ Temps traitement < 2 min par devis (vs 15-20 min manuel)

**KPIs à mesurer** :
- Répartition des CAS (1/2/3/4) - Target : 60% CAS 1, 15% CAS 2, 20% CAS 3, 5% CAS 4
- Taux validation manuelle - Target : < 20%
- Précision pricing - Target : 95% acceptation commerciale
- Temps traitement moyen - Target : < 2 min

---

## 🔧 Commandes Utiles

### Démarrer le serveur
```bash
cd c:\Users\PPZ\NOVA-SERVER
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Tester un endpoint
```bash
curl -X POST http://localhost:8000/api/sap-business/process-email-to-quote \
  -H "Content-Type: application/json" \
  -d @test_data/scenario_cas1.json
```

### Consulter la base audit
```bash
sqlite3 data/supplier_tariffs.db "SELECT * FROM pricing_decisions ORDER BY created_at DESC LIMIT 10;"
```

### Initialiser les tables
```bash
python -c "from services.pricing_audit_db import init_pricing_audit_tables; init_pricing_audit_tables()"
```

---

## ✅ Checklist de Mise en Production

**Avant activation complète** :

- [ ] Vérifier accès SAP `/Invoices` et `/PurchaseInvoices`
- [ ] Tester connexion Microsoft Graph
- [ ] Initialiser tables SQLite (`pricing_decisions`, `pricing_statistics`)
- [ ] Configurer toutes les variables d'environnement
- [ ] Tester les 4 scénarios CAS (1/2/3/4)
- [ ] Vérifier transport calculator avec produits réels
- [ ] Tester extraction PDFs emails
- [ ] Vérifier création clients automatique (INSEE/Pappers)
- [ ] Valider workflow validation commerciale
- [ ] Configurer monitoring/alertes logs
- [ ] Former équipe commerciale sur interface validation
- [ ] Préparer dashboard métriques (Phase 2)

**Déploiement progressif recommandé** :

1. **Semaine 1** : Mode shadow (calcul pricing sans utilisation)
2. **Semaine 2** : Activer CAS 1 uniquement (pas de risque)
3. **Semaine 3** : Activer CAS 3 (prix moyen)
4. **Semaine 4** : Activer CAS 2 et CAS 4 avec validation manuelle
5. **Semaine 5** : Production complète avec monitoring

---

## 📞 Support Technique

**En cas de problème** :

- Vérifier logs : `logs/app.log`
- Consulter base audit : `data/supplier_tariffs.db`
- Tester connexions : `/api/graph/test-connection`, `/api/sap-business/test-connection`
- Vérifier cache token Graph (expire 60 min)
- Valider permissions Azure AD pour SAP Service Layer

**Contact développement** :
- Logs détaillés disponibles avec niveau DEBUG
- Tous les appels SAP loggés avec temps de réponse
- Décisions pricing sauvegardées avec justification complète
