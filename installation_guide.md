# 🔍 Guide d'Installation - Agent de Recherche d'Entreprises NOVA

## 📋 Prérequis

- ✅ NOVA serveur opérationnel
- ✅ Python 3.9+ avec venv activé
- ✅ PostgreSQL configuré
- ✅ Accès aux APIs INSEE et Pappers

## 🚀 Installation Étape par Étape

### **Étape 1 : Préparation des Fichiers**

#### 1.1 Créer les nouveaux fichiers

```bash
# Depuis le répertoire NOVA-SERVER
cd C:\Users\PPZ\NOVA-SERVER

# Créer les fichiers services
touch services/company_agent.py
touch services/company_search_service.py

# Créer les fichiers routes
touch routes/routes_company_search.py

# Créer les fichiers de test
touch tests/test_company_search_integration.py
```

#### 1.2 Copier le contenu des fichiers

1. **services/company_agent.py** ← Copier le contenu de l'artifact `company_agent_nova`
2. **services/company_search_service.py** ← Copier le contenu de l'artifact `company_search_service`
3. **routes/routes_company_search.py** ← Copier le contenu de l'artifact `routes_company_search`
4. **tests/test_company_search_integration.py** ← Copier le contenu de l'artifact `test_company_integration`

### **Étape 2 : Configuration des Dépendances**

#### 2.1 Mettre à jour requirements.txt

```bash
# Ajouter les dépendances pour l'agent de recherche
echo "unicodedata2>=14.0.0" >> requirements.txt

# Réinstaller les dépendances
pip install -r requirements.txt
```

#### 2.2 Vérifier les dépendances

```bash
# Vérifier que les modules sont importables
python -c "import unicodedata; print('unicodedata OK')"
python -c "import requests; print('requests OK')"
python -c "import json; print('json OK')"
```

### **Étape 3 : Configuration des Variables d'Environnement**

#### 3.1 Modifier le fichier .env

```bash
# Éditer le fichier .env
notepad .env

# Ajouter les variables suivantes :
INSEE_API_KEY=c83c88f1-ca96-4272-bc88-f1ca96827240
PAPPERS_API_KEY=29fbe59dd017f52bcb7bb0532d72935f3cedfa6b96123170
COMPANY_SEARCH_ENABLED=true
CLIENT_ENRICHMENT_ENABLED=true
```

#### 3.2 Vérifier la configuration

```bash
# Test de chargement des variables
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
print('INSEE_API_KEY:', os.getenv('INSEE_API_KEY'))
print('PAPPERS_API_KEY:', os.getenv('PAPPERS_API_KEY'))
"
```

### **Étape 4 : Intégration dans main.py**

#### 4.1 Modifier la configuration des modules

```python
# Ouvrir main.py et modifier MODULES_CONFIG
MODULES_CONFIG = {
    'sync': ModuleConfig('routes.routes_sync', '/sync', ['Synchronisation']),
    'products': ModuleConfig('routes.routes_products', '/products', ['Produits']),
    'devis': ModuleConfig('routes.routes_devis', '/devis', ['Devis']),
    'assistant': ModuleConfig('routes.routes_intelligent_assistant', '/api/assistant', ['Assistant Intelligent']),
    'clients': ModuleConfig('routes.routes_clients', '/clients', ['Clients']),
    'companies': ModuleConfig('routes.routes_company_search', '/companies', ['Recherche d\'entreprises'])  # NOUVEAU
}
```

#### 4.2 Ajouter les routes d'intégration

Copier le contenu de l'artifact `main_py_integration` dans main.py après la configuration des modules.

### **Étape 5 : Tests de Validation**

#### 5.1 Test d'intégration

```bash
# Exécuter le test d'intégration
python tests/test_company_search_integration.py
```

#### 5.2 Test des endpoints

```bash
# Démarrer le serveur
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Dans un autre terminal, tester les endpoints
curl -X GET "http://localhost:8000/companies/health"
curl -X GET "http://localhost:8000/companies/search/Total"
curl -X POST "http://localhost:8000/companies/validate_siren" -H "Content-Type: application/json" -d '{"siren": "542051180"}'
```

### **Étape 6 : Intégration avec le Workflow Existant**

#### 6.1 Modifier client_validator.py

```python
# Ajouter l'import en haut du fichier
from .company_search_service import company_search_service

# Ajouter les méthodes d'enrichissement
# (Copier le contenu de l'artifact client_validator_integration)
```

#### 6.2 Test d'intégration workflow

```bash
# Tester l'enrichissement client
python -c "
import asyncio
from services.company_search_service import company_search_service

async def test():
    result = await company_search_service.search_company('Total')
    print(result)

asyncio.run(test())
"
```

### **Étape 7 : Déploiement**

#### 7.1 Redémarrer les services

```bash
# Arrêter les services
pkill -f "uvicorn main:app"
pkill -f "python sap_mcp.py"
pkill -f "python salesforce_mcp.py"

# Redémarrer avec le script PowerShell
.\start_nova.ps1
```

#### 7.2 Vérifier le déploiement

```bash
# Test de santé
curl -X GET "http://localhost:8000/health"

# Test de l'agent de recherche
curl -X GET "http://localhost:8000/companies/health"

# Test d'enrichissement
curl -X POST "http://localhost:8000/enrich_client_with_company_data" \
  -H "Content-Type: application/json" \
  -d '{"client_data": {"company_name": "Total"}}'
```

## 🎯 Exemples d'Utilisation

### **Recherche d'Entreprise**

```python
# Recherche par nom
result = await company_search_service.search_company("Total")

# Recherche par SIREN
result = await company_search_service.get_company_by_siren("542051180")

# Validation SIREN
result = await company_search_service.validate_siren("542051180")
```

### **Enrichissement Client**

```python
# Enrichissement automatique
client_data = {"company_name": "Total", "email": "contact@total.com"}
enriched = await company_search_service.enrich_client_data(client_data)

# Suggestions
suggestions = await company_search_service.get_suggestions("Tot")
```

### **Intégration API**

```bash
# Recherche rapide
GET /quick_company_search/Total

# Enrichissement client
POST /enrich_client_with_company_data
{
  "client_data": {
    "company_name": "Total",
    "email": "contact@total.com"
  }
}

# Validation SIREN
POST /validate_company_siren
{
  "siren": "542051180"
}
```

## 🔧 Dépannage

### **Problèmes Courants**

#### Service non disponible
```bash
# Vérifier l'initialisation
python -c "from services.company_search_service import company_search_service; print(company_search_service.agent)"
```

#### Erreurs API
```bash
# Vérifier les clés API
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
print('INSEE OK:', bool(os.getenv('INSEE_API_KEY')))
print('PAPPERS OK:', bool(os.getenv('PAPPERS_API_KEY')))
"
```

#### Problèmes d'import
```bash
# Vérifier la structure des modules
python -c "
import sys
sys.path.append('.')
try:
    from services.company_agent import MultiSourceCompanyAgent
    print('✅ company_agent OK')
except ImportError as e:
    print('❌ company_agent:', e)
"
```

### **Logs et Monitoring**

```bash
# Vérifier les logs
tail -f logs/company_search.log

# Statistiques du cache
curl -X GET "http://localhost:8000/companies/cache/stats"

# Vider le cache si nécessaire
curl -X DELETE "http://localhost:8000/companies/cache"
```

## ✅ Validation Finale

1. **✅ Service initialisé** : `company_search_service.agent` non null
2. **✅ Routes disponibles** : `/companies/*` endpoints répondent
3. **✅ Enrichissement fonctionnel** : Données client enrichies avec SIREN
4. **✅ Validation SIREN** : Algorithme de Luhn fonctionne
5. **✅ Intégration workflow** : Compatible avec le workflow NOVA existant

## 🎉 Prochaines Étapes

1. **Intégration UI** : Ajouter des composants d'interface pour la recherche
2. **Monitoring** : Mettre en place le monitoring des performances
3. **Optimisation** : Optimiser les performances de cache et API
4. **Extension** : Ajouter d'autres sources de données (Infogreffe, etc.)

---

**🎯 L'agent de recherche d'entreprises est maintenant intégré dans NOVA !**
