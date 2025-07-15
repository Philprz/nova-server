# 🔄 Fallback API Sirene - Guide d'utilisation

## 📋 **Vue d'ensemble**

Le système NOVA dispose maintenant d'un **fallback automatique** quand l'API Sirene n'est pas disponible. Au lieu d'échouer, l'assistant guide l'utilisateur vers une **saisie manuelle** des informations client.

## 🎯 **Fonctionnement**

### **Flux normal (API disponible)**
1. Utilisateur clique "Créer un nouveau client"
2. Extraction des informations via LLM
3. Recherche automatique via API Sirene/INSEE
4. Affichage des résultats trouvés
5. Sélection et création du client

### **Flux fallback (API indisponible)**
1. Utilisateur clique "Créer un nouveau client"
2. Extraction des informations via LLM
3. ⚠️ **Détection d'erreur API** (timeout, connexion, etc.)
4. 🔄 **Activation automatique du fallback**
5. Affichage du formulaire de saisie manuelle
6. Guidage utilisateur pour saisir les champs obligatoires
7. Validation locale et création directe

## 🛠️ **Champs du formulaire manuel**

### **Obligatoires**
- ✅ **Nom de l'entreprise** (requis pour Salesforce)

### **Recommandés**
- 📞 **Nom du contact**
- 📧 **Email**
- 📱 **Téléphone**
- 🏠 **Adresse**
- 🏙️ **Ville**
- 📮 **Code postal**
- 🏢 **SIRET** (optionnel)

## 🔧 **Détection automatique des erreurs**

Le système détecte automatiquement :
- **Timeouts API**
- **Erreurs de connexion**
- **Services indisponibles**
- **Erreurs d'authentification**

## 💡 **Avantages**

✅ **Continuité de service** - Pas d'interruption même si l'API est down
✅ **Expérience utilisateur fluide** - Guidage automatique vers la solution
✅ **Validation locale** - Contrôles basiques sans API externe
✅ **Données complètes** - Possibilité de saisir toutes les informations nécessaires

## 🧪 **Test du fallback**

Pour tester le fallback, le système simule aléatoirement des erreurs API (30% de chance en mode POC).

En production, le fallback se déclenche automatiquement lors de vraies pannes d'API.

## 📝 **Notes techniques**

- **Route principale** : `/api/assistant/create_client/from_text`
- **Route fallback** : `/api/assistant/create_client/manual`
- **Validation** : Locale + basique (email, téléphone, SIRET)
- **Intégration** : Création directe dans Salesforce sans validation externe

## 🎨 **Interface utilisateur**

- **Formulaire responsive** avec validation en temps réel
- **Messages d'erreur clairs** et contextuels
- **Design cohérent** avec l'interface NOVA
- **Accessibilité** optimisée (labels, focus, etc.)