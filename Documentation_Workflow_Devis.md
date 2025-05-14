# Documentation du Workflow de Devis NOVA

## Vue d'ensemble

Le workflow de devis NOVA est un système d'orchestration permettant de générer des devis intelligents à partir de demandes en langage naturel. Il intègre:

1. Claude (LLM) pour l'analyse des demandes
2. Salesforce pour la gestion des clients et des devis
3. SAP Business One pour les informations produits et la gestion des stocks

## Architecture du workflow

1. **Réception de la demande** - Le commercial formule une demande en langage naturel
2. **Extraction des informations** - Claude analyse la demande et extrait les informations clés
3. **Validation du client** - Vérification de l'existence du client dans Salesforce
4. **Récupération des informations produits** - Interrogation de SAP pour les détails produits et stocks
5. **Vérification de la disponibilité** - Contrôle des stocks et recherche d'alternatives si nécessaire
6. **Création du devis** - Préparation et création du devis dans Salesforce
7. **Réponse au commercial** - Présentation du résultat avec recommandations

## Intégration avec les systèmes

### Claude (LLM)
- Utilisé pour l'extraction d'informations structurées depuis les demandes en langage naturel
- Connecté via l'API Anthropic avec le modèle Claude 3 Opus

### Salesforce
- Validation des clients (Accounts)
- Création et mise à jour des devis
- Interface utilisateur via Lightning Web Component
- Connecté via l'outil MCP `salesforce_mcp`

### SAP Business One
- Récupération des informations produits (détails, prix)
- Vérification des stocks et disponibilités
- Recherche d'alternatives pour les produits indisponibles
- Connecté via l'outil MCP `sap_mcp`

## API REST

Le workflow expose les endpoints suivants:

### POST /generate_quote
Génère un devis à partir d'une demande en langage naturel

**Paramètres:**
```json
{
  "prompt": "String - La demande en langage naturel",
  "draft_mode": "Boolean - Mode brouillon (optionnel, défaut: false)"
}
**Réponse:**
```json
{
  "status": "String - success ou error",
  "quote_id": "String - ID du devis généré",
  "quote_status": "String - Statut du devis (Draft, Ready, etc.)",
  "client": {
    "name": "String - Nom du client",
    "account_number": "String - Numéro de compte client"
  },
  "products": [
    {
      "code": "String - Code produit",
      "name": "String - Nom du produit",
      "quantity": "Number - Quantité demandée",
      "unit_price": "Number - Prix unitaire",
      "line_total": "Number - Total de la ligne"
    }
  ],
  "total_amount": "Number - Montant total du devis",
  "currency": "String - Devise (ex: EUR)",
  "date": "String - Date du devis (format YYYY-MM-DD)",
  "message": "String - Message informatif",
  "all_products_available": "Boolean - Tous les produits sont disponibles",
  "unavailable_products": [
    {
      "code": "String - Code produit",
      "name": "String - Nom du produit",
      "quantity_requested": "Number - Quantité demandée",
      "quantity_available": "Number - Quantité disponible",
      "reason": "String - Raison de l'indisponibilité"
    }
  ],
  "alternatives": {
    "PRODUCT_CODE": [
      {
        "ItemCode": "String - Code produit alternatif",
        "ItemName": "String - Nom du produit alternatif",
        "Price": "Number - Prix du produit alternatif",
        "Stock": "Number - Stock disponible"
      }
    ]
  }
}
POST /update_quote
Met à jour un devis avec des produits alternatifs sélectionnés
Paramètres:
json{
  "quote_id": "String - ID du devis à mettre à jour",
  "products": [
    {
      "code": "String - Code produit",
      "name": "String - Nom du produit",
      "quantity": "Number - Quantité",
      "unit_price": "Number - Prix unitaire"
    }
  ]
}
Réponse: Format identique à l'endpoint /generate_quote
Cas d'utilisation
1. Devis standard avec produits disponibles

Le commercial saisit: "faire un devis pour 10 ordinateurs portables A23567 pour le client ACME"
Le système extrait: client="ACME", produits=[{"code": "A23567", "quantity": 10}]
Le client est validé dans Salesforce
Les informations produits sont récupérées depuis SAP
La disponibilité est vérifiée (stock suffisant)
Le devis est créé dans Salesforce avec le statut "Ready"
Le commercial peut valider le devis directement

2. Devis avec produits partiellement disponibles

Le commercial saisit: "devis pour THALES incluant 2000 cartouches XYZ001"
Le système extrait: client="THALES", produits=[{"code": "XYZ001", "quantity": 2000}]
Le client est validé dans Salesforce
SAP indique que seulement 1500 unités sont disponibles
Le système recherche des alternatives dans SAP
Le devis est créé en mode brouillon
Le commercial peut sélectionner des alternatives ou ajuster les quantités

3. Devis avec client inconnu

Le commercial saisit: "devis pour 50 licences SOFT456 pour le client INEXISTANT"
Le système extrait: client="INEXISTANT", produits=[{"code": "SOFT456", "quantity": 50}]
Le client n'est pas trouvé dans Salesforce
Le système retourne une erreur avec suggestion de vérifier le nom du client

Gestion des erreurs
Le workflow implémente plusieurs niveaux de gestion des erreurs:

Validation des entrées - Vérification des paramètres de la requête
Extraction fallback - Méthode basique en cas d'échec de l'extraction LLM
Logging détaillé - Journalisation de chaque étape dans les fichiers logs
Gestion des exceptions - Capture et formatage des erreurs pour l'UI
Suggestions alternatives - Propositions de solutions en cas de problèmes

Intégration Salesforce
Le composant Lightning Web Component novaDevisGenerator permet une intégration native dans Salesforce:

Peut être ajouté aux pages d'Account, d'Opportunity ou aux onglets personnalisés
Récupère automatiquement le contexte client quand disponible
Permet l'édition des devis et la sélection d'alternatives
S'intègre avec les notifications Salesforce (toast)
Supporte la création et mise à jour des devis dans Salesforce

Limites et Améliorations futures
Limites actuelles

Extraction limitée aux références produits explicites (pas de détection d'intention)
Pas de gestion des remises et promotions
Pas d'intégration avec les catalogues de prix spécifiques aux clients
Support limité des produits configurables

Améliorations prévues

Intégration de l'historique client pour des suggestions personnalisées
Support des produits liés et up-selling automatique
Interface conversationnelle pour affiner les devis
Intégration avec le workflow d'approbation Salesforce
Gestion des devis multi-devises


### Étape 15: Mise à jour du script de démarrage pour inclure le nouveau workflow

Créons un script qui va démarrer tous les composants nécessaires:

```powershell
# start_nova_devis.ps1

param (
    [switch]$Verbose
)

# Fonction d'affichage
function Write-Log {
    param (
        [string]$Message,
        [string]$Color = "White"
    )
    
    if ($Verbose) {
        Write-Host $Message -ForegroundColor $Color
    }
}

# Chemin du projet
$projectPath = $PSScriptRoot
Set-Location -Path $projectPath
Write-Log "Répertoire projet: $projectPath" -Color "Blue"

# Créer les dossiers nécessaires s'ils n'existent pas
$foldersToCreate = @("logs", "cache", "workflow")
foreach ($folder in $foldersToCreate) {
    if (-not (Test-Path $folder)) {
        New-Item -Path $folder -ItemType Directory -Force | Out-Null
        Write-Log "Dossier $folder créé" -Color "Green"
    }
}

# Activer environnement virtuel
$venvPath = Join-Path $projectPath "venv\Scripts\Activate.ps1"
if (Test-Path $venvPath) {
    . $venvPath
    Write-Log "Environnement virtuel activé" -Color "Green"
} 
else {
    Write-Host "Environnement virtuel non trouvé: $venvPath" -ForegroundColor "Red"
    Write-Host "Voulez-vous continuer? (O/N)"
    $reponse = Read-Host
    if ($reponse -ne "O" -and $reponse -ne "o") {
        exit 1
    }
}

# Vérifier/installer les dépendances
$packagesToCheck = @("httpx", "fastapi", "uvicorn", "python-dotenv", "mcp")
foreach ($package in $packagesToCheck) {
    try {
        $result = python -c "import $package; print('OK')" 2>$null
        if ($result -ne "OK") {
            Write-Log "Installation de $package..." -Color "Yellow"
            pip install $package
        }
    }
    catch {
        Write-Log "Installation de $package..." -Color "Yellow"
        pip install $package
    }
}

# Charger variables d'environnement
$envFile = Join-Path $projectPath ".env"
if (Test-Path $envFile) {
    Write-Log "Chargement des variables d'environnement" -Color "Yellow"
    
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^[\s]*([^#].+?)=(.*)$') {
            $key = $matches[1].Trim()
            $value = $matches[2].Trim()
            [System.Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
    
    Write-Log "Variables chargées" -Color "Green"
}
else {
    Write-Host "Fichier .env non trouvé" -ForegroundColor "Yellow"
}

# Démarrer FastAPI
try {
    if (Get-Process -Name "uvicorn" -ErrorAction SilentlyContinue) {
        $processId = (Get-Process -Name "uvicorn").Id
        Write-Log "FastAPI déjà en cours (PID: $processId)" -Color "Cyan"
    } 
    else {
        Write-Log "Démarrage FastAPI..." -Color "Yellow"
        Start-Process -NoNewWindow -FilePath python -ArgumentList "-m uvicorn main:app --reload" -ErrorAction Stop
        Write-Host "FastAPI démarré" -ForegroundColor "Green"
    }
}
catch {
    Write-Host "Erreur de démarrage FastAPI: $_" -ForegroundColor "Red"
}

# Démarrer MCP Salesforce
try {
    $procSalesforce = Get-Process -Name "python" -ErrorAction SilentlyContinue | 
                     Where-Object { $_.Path -match "salesforce_mcp\.py" }

    if ($procSalesforce) {
        Write-Log "MCP Salesforce déjà en cours (PID: $($procSalesforce.Id))" -Color "Cyan"
    } 
    else {
        Write-Log "Démarrage MCP Salesforce..." -Color "Yellow"
        Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", 
                      "python salesforce_mcp.py" -ErrorAction Stop
        Write-Host "MCP Salesforce démarré" -ForegroundColor "Green"
    }
}
catch {
    Write-Host "Erreur de démarrage MCP Salesforce: $_" -ForegroundColor "Red"
}

# Démarrer MCP SAP
try {
    $procSAP = Get-Process -Name "python" -ErrorAction SilentlyContinue | 
               Where-Object { $_.Path -match "sap_mcp\.py" }

    if ($procSAP) {
        Write-Log "MCP SAP déjà en cours (PID: $($procSAP.Id))" -Color "Cyan"
    } 
    else {
        Write-Log "Démarrage MCP SAP..." -Color "Yellow"
        Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", 
                      "python sap_mcp.py" -ErrorAction Stop
        Write-Host "MCP SAP démarré" -ForegroundColor "Green"
    }
}
catch {
    Write-Host "Erreur de démarrage MCP SAP: $_" -ForegroundColor "Red"
}

# Recapitulatif
Write-Host ""
Write-Host "Recapitulatif des services NOVA Middleware:" -ForegroundColor "Cyan"
Write-Host "-----------------------------------------------" -ForegroundColor "Cyan"
Write-Host "* FastAPI  : http://localhost:8000/" -ForegroundColor "Green"
Write-Host "* API Devis: http://localhost:8000/generate_quote" -ForegroundColor "Green"
Write-Host "* MCP Salesforce : Actif" -ForegroundColor "Green"
Write-Host "* MCP SAP        : Actif" -ForegroundColor "Green"
Write-Host "-----------------------------------------------" -ForegroundColor "Cyan"
Write-Host "Pour tester, utilisez la collection Postman ou l'interface Salesforce" -ForegroundColor "Magenta"