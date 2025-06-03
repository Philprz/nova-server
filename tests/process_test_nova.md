# Guide de test du projet NOVA Middleware

Suivez ces étapes pour vérifier le bon fonctionnement du système:

## 1. Vérification de l'environnement

Ouvrez PowerShell et exécutez:

```powershell
cd CHEMIN_VERS_VOTRE_PROJET\NOVA-SERVER
.\venv\Scripts\Activate.ps1
python -c "import sys; print(f'Python {sys.version}')"
```

Vérifiez que Python 3.9+ est bien installé et l'environnement virtuel activé.

## 2. Démarrage des services

Lancez le script de démarrage global:

```powershell
.\start_nova.ps1
```

Ce script devrait (vérifiez son contenu si besoin) :
- Activer l'environnement virtuel
- Démarrer les serveurs MCP pour Salesforce et SAP
- Lancer l'API FastAPI sur le port 8000 (par défaut)

Ce script va:
- Activer l'environnement virtuel
- Vérifier les dépendances
- Démarrer les serveurs MCP pour Salesforce et SAP
- Lancer l'API FastAPI sur le port 8000

Alternativement, vous pouvez démarrer les services manuellement (voir `README.md` pour les commandes détaillées).

## 3. Vérification des Composants

### Diagnostic de la Base de Données
Assurez-vous que la base de données est correctement configurée et que les migrations Alembic sont à jour :
```powershell
python tests\diagnostic_db.py
```

### Health Check de l'API
Ouvrez votre navigateur ou utilisez un client API (comme Postman ou curl) pour vérifier que l'API FastAPI est accessible :
`http://localhost:8000/`

Vous devriez également pouvoir accéder à la documentation Swagger/OpenAPI :
`http://localhost:8000/docs`

## 4. Tests Fonctionnels

### Test de Génération de Devis Simple
Exécutez le script de test pour un workflow de devis basique :
```powershell
python tests\test_devis_generique.py "faire un devis pour 500 ref A00002 pour le client Edge Communications"
```
Adaptez la requête en langage naturel selon vos besoins de test.

### Test du Workflow Enrichi (avec création/validation client)
Pour tester le processus complet incluant la création de client et les validations :
```powershell
python workflow\test_enriched_workflow.py
```
Ce script peut nécessiter une configuration ou des prompts spécifiques, référez-vous à son contenu pour les détails.

## 5. Tests via API (Exemples)

Utilisez un client API pour interagir directement avec les endpoints :

- **POST** `/generate_quote`
  - Body (JSON) : `{"query": "votre requête en langage naturel"}`
- **POST** `/create_client`
  - Body (JSON) : (Référez-vous à la structure attendue, ex: `{"natural_language_query": "Créer client Dupont SAS..."}` ou une structure de données client plus détaillée)
- **GET** `/search_clients?query=...`

Consultez la documentation Swagger (`/docs`) pour les détails exacts des requêtes et réponses.

## 6. Vérification des Logs

Consultez les fichiers dans le répertoire `logs/` (si des logs y sont configurés) et la sortie console des serveurs MCP et FastAPI pour identifier d'éventuelles erreurs ou avertissements.