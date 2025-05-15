# Guide de test du projet NOVA Middleware

Suivez ces étapes pour vérifier le bon fonctionnement du système:

## 1. Vérification de l'environnement

Ouvrez PowerShell et exécutez:

```powershell
cd C:\Users\PPZ\NOVA
.\venv\Scripts\Activate.ps1
python -c "import sys; print(f'Python {sys.version}')"
```

Vérifiez que Python 3.10+ est bien installé et l'environnement virtuel activé.

## 2. Démarrage des services

Lancez le script de démarrage optimisé:

```powershell
.\start_nova_devis.ps1 -Verbose
```

Ce script va:
- Activer l'environnement virtuel
- Vérifier les dépendances
- Démarrer les serveurs MCP pour Salesforce et SAP
- Lancer l'API FastAPI sur le port 8000

## 3. Test des connexions

Vérifiez les connexions aux systèmes externes:

```powershell
python tests\test_salesforce_connection.py
python tests\test_sap_connection.py
```

Vous devriez voir des messages confirmant les connexions.

## 4. Test du workflow de devis

### Option 1: Via Postman

1. Ouvrez Postman et importez la collection:
   `postman\NOVA_WORKFLOW_Test.json`

2. Exécutez la requête "Générer un devis"

### Option 2: Via navigateur web

1. Ouvrez http://localhost:8000/static/demo_devis.html
2. Saisissez la demande: "faire un devis pour 500 ref A00001 pour le client Edge Communications"
3. Cliquez sur "Générer le devis"

### Option 3: Via ligne de commande

```powershell
cd C:\Users\PPZ\NOVA
python tests\test_direct_api.py
```

## 5. Test de Claude avec MCP

1. Ouvrez Claude Desktop
2. Vérifiez que les outils MCP sont disponibles (icône "+")
3. Testez la commande simple:
   ```
   ping
   ```
4. Testez une requête Salesforce:
   ```
   salesforce_query("SELECT Id, Name FROM Account LIMIT 5")
   ```

## 6. Vérification des logs

Consultez les logs pour identifier d'éventuelles erreurs:

```powershell
Get-Content .\logs\workflow_devis.log -Tail 20
Get-Content .\logs\salesforce_mcp.log -Tail 20
Get-Content .\logs\sap_mcp.log -Tail 20
```

## 7. Résolution des problèmes courants

- **Erreur de connexion Salesforce**: Vérifiez les credentials dans .env
- **Erreur de connexion SAP**: Vérifiez l'URL et les identifiants
- **Serveur MCP non trouvé**: Vérifiez le fichier claude_desktop_config.json

Besoin d'aide supplémentaire?