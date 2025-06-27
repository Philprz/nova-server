# 👥 Manuel Utilisateur - POC NOVA

## 🎯 Qu'est-ce que NOVA ?

**NOVA** est votre assistant intelligent pour générer automatiquement des devis. Il suffit de formuler votre demande en langage naturel, comme vous le feriez avec un collègue !

### ✨ **Avantages pour les Commerciaux**
- 🚀 **Gain de temps** : Devis généré en moins de 2 minutes
- 🎯 **Précision** : Prix et stocks temps réel depuis SAP
- 🔄 **Automatisation** : Synchronisation Salesforce automatique
- 🌐 **Simplicité** : Commandes en français ou anglais

---

## 🗣️ Comment Formuler Votre Demande

### 📝 **Format de Base**
```
"faire un devis pour [QUANTITÉ] [RÉFÉRENCE] pour le client [NOM_CLIENT]"
```

### ✅ **Exemples Valides**

#### **🇫🇷 Français**
```
✅ "faire un devis pour 100 unités de A00001 pour le client Edge Communications"
✅ "devis pour 500 ref A00002 pour SAFRAN"
✅ "générer un devis : 250 A00001 + 150 A00002 pour Orange"
✅ "je veux un devis pour Airbus avec 1000 pièces A00001"
```

#### **🇬🇧 Anglais**
```
✅ "quote for 200 items A00001 for Edge Communications"
✅ "create quote for IBM with 300 ref A00002"
✅ "generate quote: 100 A00001 for Microsoft"
```

#### **🔢 Multi-Produits**
```
✅ "devis pour NOVA Corp avec 50 A00001 et 75 A00002"
✅ "faire un devis pour Total : 200 ref A00001 + 100 ref A00002"
```

### ❌ **À Éviter**
```
❌ "bonjour comment allez-vous ?"          → Pas de demande de devis
❌ "devis pour 100"                        → Produit manquant
❌ "faire un devis pour A00001"            → Client manquant
❌ "client Edge Communications"            → Quantité et produit manquants
```

---

## 🎮 Interface Utilisateur

### 🖥️ **Interface Web (Démo)**

Accédez à : `http://localhost:8000/static/demo_devis.html`

```
┌─────────────────────────────────────────┐
│  🚀 NOVA - Générateur de Devis IA      │
├─────────────────────────────────────────┤
│                                         │
│  📝 Votre demande:                      │
│  ┌─────────────────────────────────────┐ │
│  │ faire un devis pour 100 ref A00001 │ │
│  │ pour le client Edge Communications │ │
│  └─────────────────────────────────────┘ │
│                                         │
│         [🚀 Générer le Devis]          │
│                                         │
└─────────────────────────────────────────┘
```

### 📱 **API REST (Intégration)**

```bash
curl -X POST "http://localhost:8000/generate_quote" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: votre_cle_api" \
  -d '{
    "prompt": "faire un devis pour 100 ref A00001 pour Edge Communications"
  }'
```

---

## 📊 Comprendre les Réponses

### ✅ **Devis Généré avec Succès**

```json
{
  "status": "success",
  "quote_id": "SAP-376",
  "client": {
    "name": "Edge Communications",
    "account_number": "CD451796",
    "salesforce_id": "0014000000ABC123"
  },
  "products": [
    {
      "code": "A00001",
      "name": "Produit Standard",
      "quantity": 100,
      "unit_price": 40.00,
      "line_total": 4000.00
    }
  ],
  "total_amount": 4000.00,
  "currency": "EUR",
  "date": "2025-06-04",
  "message": "Devis créé avec succès",
  "all_products_available": true
}
```

#### **📋 Informations Retournées**
- 🆔 **ID Devis** : Référence SAP (ex: SAP-376)
- 👤 **Client** : Nom + numéro de compte
- 📦 **Produits** : Code, nom, quantité, prix unitaire
- 💰 **Total** : Montant total HT en euros
- 📅 **Date** : Date de génération
- ✅ **Disponibilité** : Tous produits disponibles

### ⚠️ **Produits Partiellement Disponibles**

```json
{
  "status": "success",
  "all_products_available": false,
  "unavailable_products": [
    {
      "code": "A00002",
      "name": "Produit Limité",
      "quantity_requested": 500,
      "quantity_available": 250,
      "reason": "Stock insuffisant"
    }
  ],
  "alternatives": {
    "A00002": [
      {
        "ItemCode": "A00003",
        "ItemName": "Produit Alternative",
        "Price": 45.00,
        "Stock": 1000
      }
    ]
  }
}
```

#### **🔄 Actions Recommandées**
1. **Ajuster les quantités** selon le stock disponible
2. **Choisir une alternative** proposée
3. **Diviser la commande** en plusieurs livraisons

### ❌ **Erreurs Courantes**

#### **Client Non Trouvé**
```json
{
  "status": "error",
  "message": "Client 'XYZ Corp' non trouvé dans Salesforce",
  "next_steps": "Veuillez vérifier le nom du client et réessayer."
}
```
**💡 Solution** : Vérifiez l'orthographe ou utilisez le nom complet

#### **Produit Inexistant**
```json
{
  "status": "error",
  "message": "Produit 'Z99999' non trouvé dans SAP",
  "next_steps": "Vérifiez la référence produit dans le catalogue."
}
```
**💡 Solution** : Consultez le catalogue SAP pour la bonne référence

---

## 🎯 Scénarios d'Usage Courants

### 📋 **Scénario 1 : Devis Simple**

**Demande** : `"faire un devis pour 50 ref A00001 pour Edge Communications"`

**Processus** :
1. ✅ Recherche client "Edge Communications" → Trouvé
2. ✅ Récupération produit A00001 → Prix: 40€, Stock: 100
3. ✅ Vérification stock (50 demandés vs 100 disponibles) → OK
4. ✅ Création devis SAP → DocNum: 376
5. ✅ Création opportunité Salesforce → Montant: 2000€

**Résultat** : Devis généré en 45 secondes ⚡

### 📋 **Scénario 2 : Nouveau Client (Auto-Création)**

**Demande** : `"devis pour NOVA-TEST-2025 SARL avec 25 ref A00001"`

**Processus** :
1. ❌ Recherche client "NOVA-TEST-2025 SARL" → Non trouvé
2. 🔄 **Activation validation enrichie** :
   - Détection pays : France (SARL)
   - Validation format entreprise : OK
   - Contrôle doublons : Aucun
   - Enrichissement données automatique
3. ✅ Création client Salesforce → ID: 001ABC123
4. ✅ Création client SAP → CardCode: CNOVATEST2025
5. ✅ Récupération produit A00001 → Prix: 40€, Stock: 100
6. ✅ Création devis complet → Total: 1000€

**Résultat** : Client créé + devis généré en 2 minutes ⚡

### 📋 **Scénario 3 : Rupture de Stock avec Alternatives**

**Demande** : `"faire un devis pour 500 ref A00002 pour SAFRAN"`

**Processus** :
1. ✅ Client "SAFRAN" trouvé
2. ⚠️ Produit A00002 : Stock disponible = 250 (500 demandés)
3. 🔍 Recherche automatique d'alternatives :
   - A00003 : Prix 45€, Stock 1000 ✅
   - A00004 : Prix 42€, Stock 500 ✅
4. 📋 Devis créé avec stock disponible (250) + alternatives proposées

**Résultat** : Options multiples présentées pour décision commerciale

### 📋 **Scénario 4 : Multi-Produits International**

**Demande** : `"quote for Microsoft Corp with 100 A00001 and 200 A00002"`

**Processus** :
1. ✅ Détection langue anglaise
2. ✅ Client "Microsoft Corp" trouvé
3. ✅ Produit A00001 : 100 × 40€ = 4000€
4. ✅ Produit A00002 : 200 × 35€ = 7000€
5. ✅ Devis total : 11000€ avec 2 lignes

**Résultat** : Devis multi-lignes en contexte international

---

## 🔧 Fonctionnalités Avancées

### 🔍 **Recherche de Clients**

Si vous ne trouvez pas un client, utilisez l'endpoint de recherche :

```
GET /search_clients?q=Edge&source=both&limit=10
```

**Réponse** :
```json
{
  "query": "Edge",
  "salesforce": [
    {
      "Id": "001ABC123",
      "Name": "Edge Communications",
      "Phone": "+33 1 23 45 67 89",
      "BillingCity": "Paris"
    }
  ],
  "sap": [
    {
      "CardCode": "CD451796",
      "CardName": "Edge Communications", 
      "Phone1": "+33 1 23 45 67 89"
    }
  ],
  "total": 2
}
```

### 🛠️ **Création Manuelle de Client**

Pour créer un client avec plus de détails :

```json
POST /create_client
{
  "company_name": "NOVA Test Company",
  "industry": "Technology",
  "phone": "+33 1 23 45 67 89",
  "email": "contact@novatest.com",
  "billing_street": "123 Rue de Test",
  "billing_city": "Paris",
  "billing_postal_code": "75001",
  "billing_country": "France",
  "create_in_sap": true,
  "create_in_salesforce": true
}
```

### 📊 **Mise à Jour de Devis**

Pour modifier un devis existant :

```json
POST /update_quote
{
  "quote_id": "SAP-376",
  "products": [
    {
      "code": "A00003",
      "name": "Produit Alternative",
      "quantity": 500,
      "unit_price": 45.00
    }
  ]
}
```

---

## 🚨 Résolution de Problèmes

### 🔴 **Problèmes Fréquents**

#### **"Client non trouvé"**
**Causes possibles** :
- ❌ Orthographe incorrecte
- ❌ Nom incomplet
- ❌ Client inexistant dans Salesforce

**Solutions** :
1. ✅ Vérifiez l'orthographe exacte
2. ✅ Utilisez le nom complet officiel
3. ✅ Lancez une recherche : `/search_clients?q=nom_partiel`
4. ✅ Créez le client si nécessaire

#### **"Produit non trouvé"**
**Causes possibles** :
- ❌ Référence incorrecte
- ❌ Produit obsolète
- ❌ Produit non dans le catalogue SAP

**Solutions** :
1. ✅ Vérifiez la référence dans SAP
2. ✅ Consultez le catalogue produits
3. ✅ Demandez la référence mise à jour

#### **"Timeout" ou "Service Unavailable"**
**Causes possibles** :
- ❌ Surcharge système
- ❌ Problème réseau
- ❌ Service en maintenance

**Solutions** :
1. ✅ Attendez 30 secondes et réessayez
2. ✅ Vérifiez votre connexion réseau
3. ✅ Contactez le support technique

### 🟡 **Avertissements**

#### **Stock Insuffisant**
```
⚠️ "Produit A00002 : 250 disponibles sur 500 demandés"
```
**Actions** :
- 🔄 Ajustez la quantité à 250
- 🔄 Choisissez une alternative proposée
- 🔄 Divisez en plusieurs commandes

#### **Prix Manquant**
```
⚠️ "Prix par défaut utilisé pour A00001"
```
**Actions** :
- 📞 Vérifiez le tarif dans SAP
- 🔧 Mettez à jour la liste de prix
- ✏️ Corrigez manuellement si nécessaire

---

## 📈 Bonnes Pratiques

### ✅ **Pour une Efficacité Maximale**

1. **🎯 Soyez Précis** : 
   ```
   ✅ "devis pour 100 ref A00001 pour Edge Communications"
   ❌ "devis pour Edge avec des produits"
   ```

2. **📋 Utilisez les Références Exactes** :
   ```
   ✅ A00001, A00002 (références SAP)
   ❌ Produit A, Article B
   ```

3. **👥 Noms Clients Complets** :
   ```
   ✅ "Edge Communications"
   ❌ "Edge"
   ```

4. **🔢 Quantités Claires** :
   ```
   ✅ "100 unités", "250 pièces"
   ❌ "beaucoup", "quelques"
   ```

### 📚 **Commandes Utiles**

#### **Vérifications Préalables**
```bash
# État des services
GET /health

# Recherche client
GET /search_clients?q=nom_client

# Catalogue produits (via SAP)
Consultez SAP Business One directement
```

#### **Templates de Commandes**
```
📋 Devis simple :
"faire un devis pour [QTÉ] ref [CODE] pour le client [NOM]"

📋 Multi-produits :
"devis pour [CLIENT] avec [QTÉ1] [CODE1] et [QTÉ2] [CODE2]"

📋 En anglais :
"quote for [QTY] items [CODE] for [CLIENT]"
```

---

## 📞 Support et Assistance

### 🆘 **Contacts Support**

| Niveau | Contact | Disponibilité | Scope |
|--------|---------|---------------|-------|
| **Technique** | Support IT | 9h-18h | Bugs, erreurs système |
| **Fonctionnel** | Équipe Commerciale | 8h-19h | Usage, formations |
| **Urgent** | Astreinte | 24h/7j | Incidents critiques |

### 📧 **Informations à Fournir**

En cas de problème, merci de fournir :
1. 📝 **Commande exacte** utilisée
2. ⏰ **Heure** de l'incident
3. 📸 **Capture d'écran** de l'erreur
4. 🔍 **Message d'erreur** complet
5. 🌐 **Navigateur** utilisé (si interface web)

### 🔧 **Auto-Diagnostic**

Avant de contacter le support :

```bash
# 1. Vérifiez l'état des services
curl http://localhost:8000/health

# 2. Testez une commande simple
curl -X POST "http://localhost:8000/generate_quote" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "test simple"}'

# 3. Vérifiez votre connexion réseau
ping localhost
```

---

## 🎓 Formation et Ressources

### 📚 **Ressources Disponibles**

1. **📖 Documentation Technique** : Guide complet pour IT
2. **🎮 Interface de Démo** : `http://localhost:8000/static/demo_devis.html`
3. **📊 API Documentation** : `http://localhost:8000/docs`
4. **🧪 Environnement de Test** : Sandbox avec données fictives

### 🎯 **Plan de Formation Recommandé**

#### **👋 Niveau Débutant (30 min)**
1. 📝 Comprendre les commandes de base
2. 🎮 Tester avec l'interface démo
3. ✅ Réaliser 3 devis simples
4. 🔍 Interpréter les réponses

#### **⚡ Niveau Intermédiaire (1h)**
1. 🎯 Maîtriser les commandes complexes
2. 🔄 Gérer les alternatives produits
3. 👥 Créer de nouveaux clients
4. 🚨 Résoudre les problèmes courants

#### **🚀 Niveau Avancé (2h)**
1. 🔧 Utiliser l'API directement
2. 📊 Optimiser les workflows
3. 🔍 Analyser les métriques
4. 🛠️ Personnaliser les intégrations

### 🏆 **Certification Utilisateur**

**Critères de validation** :
- ✅ 10 devis générés avec succès
- ✅ 1 nouveau client créé
- ✅ 1 situation de rupture gérée
- ✅ Quiz de connaissances réussi (80%)

---

## 📊 Métriques et Suivi

### 📈 **Indicateurs de Performance**

| Métrique | Objectif | Mesure |
|----------|----------|--------|
| **Temps de génération** | <2 min | Temps moyen par devis |
| **Taux de succès** | >95% | Devis générés vs tentatives |
| **Précision client** | >98% | Clients trouvés vs recherchés |
| **Disponibilité stock** | >90% | Produits disponibles immédiatement |

### 🎯 **Objectifs Commerciaux**

- 🚀 **Gain de temps** : 70% de réduction vs processus manuel
- 📈 **Volume traité** : +50% de devis générés par jour
- ✅ **Qualité** : 99% de précision des informations
- 😊 **Satisfaction** : 95% des utilisateurs satisfaits

---

## 🔮 Évolutions Prévues

### 📅 **Prochaines Fonctionnalités**

#### **🎨 Interface Salesforce Lightning** (Q3 2025)
- 🖥️ Composant intégré dans Salesforce
- ⚡ Génération directe depuis les comptes
- 📊 Tableau de bord avec métriques

#### **🤖 IA Améliorée** (Q4 2025)
- 🧠 Apprentissage des préférences utilisateur
- 🎯 Suggestions automatiques de produits
- 📈 Analyse prédictive des ventes

#### **📱 Application Mobile** (2026)
- 📲 App native iOS/Android
- 🗣️ Commandes vocales
- 📍 Géolocalisation clients

### 🌟 **Demandes d'Amélioration**

Vos suggestions sont les bienvenues ! Contactez l'équipe avec :
- 💡 Nouvelles fonctionnalités souhaitées
- 🔧 Améliorations d'ergonomie
- 📈 Optimisations performance
- 🎯 Cas d'usage spécifiques

---

## ✅ Checklist Utilisateur

### 🚀 **Première Utilisation**
- [ ] Accès à l'interface confirmé
- [ ] Première commande testée
- [ ] Client existant vérifié
- [ ] Produit catalogue identifié
- [ ] Devis généré avec succès

### 📋 **Usage Quotidien**
- [ ] Commandes formulées clairement
- [ ] Références produits vérifiées
- [ ] Stocks contrôlés avant validation
- [ ] Clients nouveaux créés si nécessaire
- [ ] Devis transmis aux clients

### 🔧 **Résolution Problèmes**
- [ ] Messages d'erreur lus attentivement
- [ ] Solutions suggérées appliquées
- [ ] Support contacté si nécessaire
- [ ] Feedback transmis à l'équipe

---

**🎯 NOVA - Votre Assistant IA pour la Génération de Devis**

**📞 Support** : support-nova@company.com  
**📚 Documentation** : http://localhost:8000/docs  
**🎮 Interface Démo** : http://localhost:8000/static/demo_devis.html

**✨ Bonne génération de devis avec NOVA ! ✨**