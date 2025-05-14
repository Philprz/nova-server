# start_mcp_servers.ps1
param (
    [switch]$NoLogs,
    [switch]$Minimal
)

$ErrorActionPreference = "Stop"
$projectDir = $PSScriptRoot

# Fonction pour écrire un message formaté
function Write-FormattedMessage {
    param (
        [string]$Message,
        [string]$Type = "INFO"
    )
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $colors = @{
        "INFO" = "Cyan";
        "SUCCESS" = "Green";
        "WARNING" = "Yellow";
        "ERROR" = "Red";
    }
    
    $color = $colors[$Type]
    Write-Host "[$timestamp] [$Type] $Message" -ForegroundColor $color
}

# Se positionner dans le répertoire du projet
Set-Location $projectDir
Write-FormattedMessage "Répertoire du projet: $projectDir" -Type "INFO"

# Vérifier les dossiers nécessaires
$foldersToCreate = @("logs", "cache")
foreach ($folder in $foldersToCreate) {
    if (-not (Test-Path $folder)) {
        New-Item -Path $folder -ItemType Directory -Force | Out-Null
        Write-FormattedMessage "Dossier $folder créé" -Type "INFO"
    }
}

# Activer l'environnement virtuel
$venvPath = Join-Path -Path $projectDir -ChildPath "venv\Scripts\Activate.ps1"
if (Test-Path $venvPath) {
    Write-FormattedMessage "Activation de l'environnement virtuel..." -Type "INFO"
    try {
        . $venvPath
        Write-FormattedMessage "Environnement virtuel activé" -Type "SUCCESS"
    }
    catch {
        Write-FormattedMessage "Erreur lors de l'activation de l'environnement virtuel: $_" -Type "ERROR"
        exit 1
    }
}
else {
    Write-FormattedMessage "Environnement virtuel non trouvé à $venvPath" -Type "ERROR"
    exit 1
}

# Vérifier/installer les dépendances
Write-FormattedMessage "Vérification des dépendances..." -Type "INFO"
$requiredPackages = @("fastapi", "uvicorn", "simple-salesforce", "mcp", "httpx", "python-dotenv")

foreach ($package in $requiredPackages) {
    try {
        $checkPackage = python -c "import $package; print('ok')" 2>$null
        if ($checkPackage -ne "ok") {
            Write-FormattedMessage "Installation de $package..." -Type "INFO"
            pip install $package
        }
    }
    catch {
        Write-FormattedMessage "Installation de $package..." -Type "INFO"
        pip install $package
    }
}

Write-FormattedMessage "Dépendances vérifiées" -Type "SUCCESS"

# Fonction pour démarrer un processus
function Start-MCPServer {
    param (
        [string]$Name,
        [string]$ScriptPath,
        [switch]$IsMinimal
    )
    
    # Déterminer le script à exécuter
    $finalScriptPath = $ScriptPath
    if ($IsMinimal -and $Minimal) {
        $finalScriptPath = $ScriptPath -replace "\.py$", "_minimal.py"
        Write-FormattedMessage "Utilisation de la version minimale: $finalScriptPath" -Type "INFO"
    }
    
    if (-not (Test-Path $finalScriptPath)) {
        Write-FormattedMessage "Script $finalScriptPath non trouvé" -Type "ERROR"
        return
    }
    
    # Démarrer le processus
    Write-FormattedMessage "Démarrage du serveur $Name..." -Type "INFO"
    
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = "powershell"
    $startInfo.Arguments = "-NoExit -Command `"[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Set-Location '$projectDir'; . .\venv\Scripts\Activate.ps1; python $finalScriptPath`""
    $startInfo.UseShellExecute = $true
    
    [System.Diagnostics.Process]::Start($startInfo) | Out-Null
    Write-FormattedMessage "Serveur $Name démarré" -Type "SUCCESS"
}

# Démarrer les serveurs MCP
Start-MCPServer -Name "Salesforce MCP" -ScriptPath "salesforce_mcp.py" -IsMinimal
Start-MCPServer -Name "SAP MCP" -ScriptPath "sap_mcp.py" -IsMinimal

# Afficher les informations de configuration Claude Desktop
Write-FormattedMessage "Configuration Claude Desktop:" -Type "INFO"
Write-FormattedMessage "1. Dans Claude Desktop, cliquez sur le bouton '+'" -Type "INFO" 
Write-FormattedMessage "2. Ajoutez les serveurs MCP 'salesforce_mcp' et 'sap_mcp'" -Type "INFO"
Write-FormattedMessage "3. Testez avec 'ping' pour vérifier la connexion" -Type "INFO"

Write-FormattedMessage "Tous les serveurs MCP sont démarrés" -Type "SUCCESS"