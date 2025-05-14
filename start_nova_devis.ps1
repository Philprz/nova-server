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