# Script minimaliste de demarrage NOVA
# Sans caracteres speciaux pour eviter les problemes d'encodage

param(
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
$projectPath = "C:\Users\PPZ\NOVA"
Set-Location -Path $projectPath
Write-Log "Repertoire projet: $projectPath" -Color "Blue"

# Activer environnement virtuel
$venvPath = Join-Path $projectPath "venv\Scripts\Activate.ps1"
if (Test-Path $venvPath) {
    . $venvPath
    Write-Log "Environnement virtuel active" -Color "Green"
} 
else {
    Write-Host "Environnement virtuel non trouve: $venvPath" -ForegroundColor "Red"
    Write-Host "Voulez-vous continuer? (O/N)"
    $reponse = Read-Host
    if ($reponse -ne "O" -and $reponse -ne "o") {
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
    
    Write-Log "Variables chargees" -Color "Green"
}
else {
    Write-Host "Fichier .env non trouve" -ForegroundColor "Yellow"
}

# Demarrer FastAPI
try {
    if (Get-Process -Name "uvicorn" -ErrorAction SilentlyContinue) {
        $processId = (Get-Process -Name "uvicorn").Id
        Write-Log "FastAPI deja en cours (PID: $processId)" -Color "Cyan"
    } 
    else {
        Write-Log "Demarrage FastAPI..." -Color "Yellow"
        Start-Process -NoNewWindow -FilePath python -ArgumentList "-m uvicorn main:app --reload" -ErrorAction Stop
        Write-Host "FastAPI demarre" -ForegroundColor "Green"
    }
}
catch {
    Write-Host "Erreur de demarrage FastAPI: $_" -ForegroundColor "Red"
}

# Demarrer MCP
try {
    $procMcp = Get-Process -Name "python" -ErrorAction SilentlyContinue | 
               Where-Object { $_.Path -match "server_mcp\.py" }

    if ($procMcp) {
        Write-Log "Server MCP deja en cours (PID: $($procMcp.Id))" -Color "Cyan"
    } 
    else {
        Write-Log "Demarrage Server MCP..." -Color "Yellow"
        Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", 
                      "python server_mcp.py --name nova_middleware -f .env" -ErrorAction Stop
        Write-Host "Server MCP demarre" -ForegroundColor "Green"
    }
}
catch {
    Write-Host "Erreur de demarrage MCP: $_" -ForegroundColor "Red"
}

# Claude Desktop configuration
try {
    $claudeConfigPath = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
    if (Test-Path $claudeConfigPath) {
        Write-Log "Verification config Claude Desktop..." -Color "Yellow"
        $cfg = Get-Content $claudeConfigPath | ConvertFrom-Json
        
        if ($cfg.integrations -and $cfg.integrations.nova_middleware) {
            Write-Log "Integration 'nova_middleware' deja configuree" -Color "Green"
        } 
        else {
            Write-Log "Installation de 'nova_middleware'..." -Color "Yellow"
            Write-Host "Tentative d'installation nova_middleware..." -ForegroundColor "Yellow"
            try {
                mcp install nova_middleware --config "$claudeConfigPath"
                Write-Host "nova_middleware ajoute a Claude Desktop" -ForegroundColor "Green"
            }
            catch {
                Write-Host "Erreur d'installation: $_" -ForegroundColor "Red"
                Write-Host "Installez manuellement nova_middleware" -ForegroundColor "Yellow"
            }
        }
    } 
    else {
        Write-Host "Config Claude Desktop introuvable: $claudeConfigPath" -ForegroundColor "Yellow"
        Write-Host "Veuillez installer manuellement nova_middleware dans Claude Desktop." -ForegroundColor "Yellow"
    }
}
catch {
    Write-Host "Erreur de configuration Claude: $_" -ForegroundColor "Red"
}

# Recapitulatif
Write-Host ""
Write-Host "Recapitulatif des services NOVA Middleware:" -ForegroundColor "Cyan"
Write-Host "-----------------------------------------------" -ForegroundColor "Cyan"
Write-Host "* FastAPI  : http://localhost:8000/" -ForegroundColor "Green"
Write-Host "* MCP      : nova_middleware" -ForegroundColor "Green"
if (Test-Path $envFile) {
    Write-Host "* PostgreSQL : $env:DB_NAME@$env:DB_HOST" -ForegroundColor "Green"
}
Write-Host "-----------------------------------------------" -ForegroundColor "Cyan"
Write-Host "Pour integrer dans Claude Desktop:" -ForegroundColor "Magenta"
Write-Host "1. Redemarrez Claude Desktop si necessaire" -ForegroundColor "Magenta"
Write-Host "2. Cliquez sur '+' et choisissez 'nova_middleware'" -ForegroundColor "Magenta"
Write-Host "3. Testez via la commande ping" -ForegroundColor "Magenta"