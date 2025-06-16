# Script de démarrage NOVA

param(
    [switch]$Verbose,
    [switch]$SkipTests,
    [switch]$SapOnly,
    [switch]$NoClaudeDesktop
)

function Write-Header {
    param (
        [string]$Message
    )
    
    Write-Host ""
    Write-Host "===================================================" -ForegroundColor Cyan
    Write-Host $Message -ForegroundColor Cyan
    Write-Host "===================================================" -ForegroundColor Cyan
}

function Write-Log {
    param (
        [string]$Message,
        [string]$Color = "White"
    )
    
    if ($Verbose) {
        Write-Host $Message -ForegroundColor $Color
    } else {
        Write-Host "." -NoNewline -ForegroundColor $Color
    }
}

function Test-Command {
    param (
        [string]$Command
    )
    
    try {
        Invoke-Expression "Get-Command $Command -ErrorAction Stop | Out-Null"
        return $true
    } catch {
        return $false
    }
}

# Bannière
Clear-Host
Write-Host @"
╔═══════════════════════════════════════════════════╗
║                                                   ║
║   ███╗   ██╗ ██████╗ ██╗   ██╗ █████╗             ║
║   ████╗  ██║██╔═══██╗██║   ██║██╔══██╗            ║
║   ██╔██╗ ██║██║   ██║██║   ██║███████║            ║
║   ██║╚██╗██║██║   ██║╚██╗ ██╔╝██╔══██║            ║
║   ██║ ╚████║╚██████╔╝ ╚████╔╝ ██║  ██║            ║
║   ╚═╝  ╚═══╝ ╚═════╝   ╚═══╝  ╚═╝  ╚═╝            ║
║                                                   ║
║   Middleware d'intégration LLM - SAP - Salesforce ║
║   v1.0.0 - IT Spirit - 2025                       ║
║                                                   ║
╚═══════════════════════════════════════════════════╝
"@ -ForegroundColor Yellow

# Chemin du projet et des exécutables
$projectPath = $PSScriptRoot
Set-Location -Path $projectPath
Write-Log "Répertoire projet: $projectPath" -Color "Blue"

# Vérification de l'environnement
Write-Header "PRÉPARATION DE L'ENVIRONNEMENT"

# Créer les dossiers requis s'ils n'existent pas
$requiredFolders = @("logs", "cache")
foreach ($folder in $requiredFolders) {
    if (-not (Test-Path $folder)) {
        New-Item -ItemType Directory -Path $folder | Out-Null
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
    Write-Host "Création d'un nouvel environnement virtuel..." -ForegroundColor "Yellow"
    
    # Vérifier si Python est installé
    if (Test-Command "python") {
        python -m venv venv
        if ($?) {
            . $venvPath
            Write-Log "Nouvel environnement virtuel créé et activé" -Color "Green"
            
            # Mettre à jour pip
            python -m pip install --upgrade pip
            
            # Installer les dépendances
            if (Test-Path "requirements.txt") {
                pip install -r requirements.txt
                Write-Log "Dépendances installées" -Color "Green"
            }
        } else {
            Write-Host "Échec de la création de l'environnement virtuel" -ForegroundColor "Red"
            exit 1
        }
    } else {
        Write-Host "Python n'est pas installé ou n'est pas dans le PATH" -ForegroundColor "Red"
        exit 1
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
    # TODO: Proposer de créer un fichier .env par défaut
}

# Vérification des dépendances critiques
$criticalDeps = @("mcp", "fastapi", "sqlalchemy", "simple_salesforce", "httpx", "uvicorn")
$missingDeps = @()

foreach ($dep in $criticalDeps) {
    try {
        python -c "import $dep" 2>$null
        Write-Log "Dépendance $dep disponible" -Color "Green"
    } catch {
        Write-Host "Dépendance manquante: $dep" -ForegroundColor "Yellow"
        $missingDeps += $dep
    }
}

if ($missingDeps.Count -gt 0) {
    Write-Host "Installation des dépendances manquantes..." -ForegroundColor "Yellow"
    foreach ($dep in $missingDeps) {
        pip install $dep
    }
}

# Démarrage des services
Write-Header "DÉMARRAGE DES SERVICES"

# Démarrer le serveur MCP SAP
Write-Log "Démarrage du serveur MCP SAP..." -Color "Yellow"
Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", 
    "python sap_mcp.py"

# Si non limité à SAP uniquement, démarrer les autres composants
if (-not $SapOnly) {
    # Démarrer le serveur MCP Salesforce
    Write-Log "Démarrage du serveur MCP Salesforce..." -Color "Yellow"
    Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", 
        "python salesforce_mcp.py"
        
    # Démarrer FastAPI
    Write-Log "Démarrage du serveur FastAPI..." -Color "Yellow"
    Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", 
        "uvicorn main:app --reload --host 0.0.0.0 --port 8000"
}

# Laisser le temps aux services de démarrer
Write-Host "Démarrage des services en cours..." -ForegroundColor "Yellow"
Start-Sleep -Seconds 5

# Si demandé, ouvrir Claude Desktop automatiquement
if (-not $NoClaudeDesktop) {
    $claudeDesktopPath = "$env:LOCALAPPDATA\Claude\Claude.exe"
    if (Test-Path $claudeDesktopPath) {
        Write-Log "Démarrage de Claude Desktop..." -Color "Yellow"
        Start-Process -FilePath $claudeDesktopPath
    } else {
        Write-Host "Claude Desktop non trouvé à $claudeDesktopPath" -ForegroundColor "Yellow"
    }
}

# Exécuter un test rapide si non ignoré
if (-not $SkipTests) {
    Write-Header "TEST RAPIDE"
    try {
        $testResult = python -c "import sys; sys.path.append(r'$projectPath'); from services.mcp_connector import MCPConnector; print('Connexion MCP OK')"
        if ($testResult -match "Connexion MCP OK") {
            Write-Host "✅ Test MCP réussi" -ForegroundColor "Green"
        } else {
            Write-Host "❌ Test MCP échoué" -ForegroundColor "Red"
        }
    } catch {
        Write-Host "❌ Test MCP échoué avec erreur: $_" -ForegroundColor "Red"
    }
}

# Récapitulatif
Write-Header "RÉCAPITULATIF"
Write-Host "Services démarrés :" -ForegroundColor "Cyan"
Write-Host "* MCP SAP         : Démarré" -ForegroundColor "Green"

if (-not $SapOnly) {
    Write-Host "* MCP Salesforce  : Démarré" -ForegroundColor "Green"
    Write-Host "* FastAPI         : http://localhost:8000/" -ForegroundColor "Green"
    Write-Host "* Swagger UI      : http://localhost:8000/docs" -ForegroundColor "Green"
}

Write-Host ""
Write-Host "Pour tester un workflow complet de devis :" -ForegroundColor "Magenta"
Write-Host "python test_devis_generique.py 'faire un devis pour 500 ref A00002 pour le client Edge Communications'" -ForegroundColor "White"
Write-Host ""
Write-Host "Pour ouvrir la démo web :" -ForegroundColor "Magenta"
Write-Host "http://localhost:8000/static/nova_interface.html" -ForegroundColor "White"

Write-Header "NOVA DÉMARRÉ"