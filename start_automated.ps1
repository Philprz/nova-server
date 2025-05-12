# automated_start_nouveau.ps1
param(
  [switch]$Verbose
)

# Activer le mode strict pour détecter les variables non déclarées
Set-StrictMode -Version Latest

# Débloquer l'exécution des scripts
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force

# Définir et se placer dans le répertoire du projet
$projectPath = "C:\Users\PPZ\NOVA"
Set-Location -Path $projectPath

# Fonction pour charger les variables d'environnement depuis .env
function Import-DotEnv {
    param (
        [string]$path
    )
    
    if (Test-Path $path) {
        if ($Verbose) { Write-Host "🔑 Chargement des variables d'environnement depuis .env" -ForegroundColor Yellow }
        Get-Content $path | ForEach-Object {
            if ($_ -match '^[\s]*([^#].+?)=(.*)$') {
                $key = $matches[1].Trim()
                $value = $matches[2].Trim()
                [System.Environment]::SetEnvironmentVariable($key, $value, "Process")
            }
        }
        if ($Verbose) { Write-Host "✔ Variables chargées" -ForegroundColor Green }
        return $true
    } else {
        if ($Verbose) { Write-Host "ℹ Aucun fichier .env trouvé, continuer sans" -ForegroundColor Cyan }
        return $false
    }
}

# Activer l'environnement virtuel
$venvPath = Join-Path $projectPath "venv\Scripts\Activate.ps1"
if (Test-Path $venvPath) {
    . $venvPath
    if ($Verbose) { Write-Host "✔ Environnement virtuel activé" -ForegroundColor Green }
} else {
    Write-Host "❌ Environnement virtuel non trouvé : $venvPath" -ForegroundColor Red
    exit 1
}

# Installer les dépendances Python (requirements.txt)
$requirementsPath = Join-Path $projectPath "requirements.txt"
if (Test-Path $requirementsPath) {
    if ($Verbose) { Write-Host "🚧 Installation des dépendances Python..." -ForegroundColor Yellow }
    try {
        if ($Verbose) {
            pip install -r $requirementsPath
        } else {
            pip install -r $requirementsPath | Out-Null
        }
        if ($Verbose) { Write-Host "✔ Dépendances installées" -ForegroundColor Green }
    } catch {
        Write-Host "❌ Échec de l'installation des dépendances : $_" -ForegroundColor Red
        exit 1
    }
} else {
    if ($Verbose) { Write-Host "⚠ Aucun fichier requirements.txt trouvé, passage à l'étape suivante" -ForegroundColor Cyan }
}
    
# Charger les variables d'environnement depuis .env
$envFile = Join-Path $projectPath ".env"
Import-DotEnv -path $envFile

# Vérifier la connexion à PostgreSQL
try {
    psql -h $env:DB_HOST -U $env:DB_USER -d $env:DB_NAME -c '\q' -ErrorAction Stop > $null
    if ($Verbose) { Write-Host "✔ Connexion PostgreSQL OK" -ForegroundColor Green }
} catch {
    Write-Host "❌ Erreur de connexion PostgreSQL" -ForegroundColor Red
    Write-Host "   $_" -ForegroundColor Red
    exit 1
}

# Démarrer le serveur FastAPI (uvicorn)
if (Get-Process -Name "uvicorn" -ErrorAction SilentlyContinue) {
    $processId = (Get-Process -Name "uvicorn").Id
    if ($Verbose) { Write-Host "ℹ FastAPI déjà en cours (PID : $processId)" -ForegroundColor Cyan }
} else {
    if ($Verbose) { Write-Host "🚀 Démarrage FastAPI avec uvicorn..." -ForegroundColor Yellow }
    Start-Process -NoNewWindow -FilePath python -ArgumentList "-m uvicorn main:app --reload" -ErrorAction Stop
}

# Attendre que FastAPI soit prêt sur http://localhost:8000
$maxRetries = 10
$retry = 0
$fastApiReady = $false

while (-not $fastApiReady -and $retry -lt $maxRetries) {
    try {
        Invoke-WebRequest -Uri "http://localhost:8000" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop > $null
        $fastApiReady = $true
        if ($Verbose) { Write-Host "✔ FastAPI opérationnel" -ForegroundColor Green }
    } catch {
        $retry++
        if ($Verbose) { Write-Host "⏳ Attente FastAPI (tentative $retry/$maxRetries)..." -ForegroundColor Yellow }
        Start-Sleep -Seconds 2
    }
}

if (-not $fastApiReady) {
    Write-Host "⚠ FastAPI non disponible après $maxRetries tentatives" -ForegroundColor Magenta
}

# Démarrer le serveur MCP (server_mcp.py) dans une session PowerShell séparée
$procMcp = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object { $_.Path -match "server_mcp\.py" }

if ($procMcp) {
    if ($Verbose) { Write-Host "ℹ Server MCP déjà en cours (PID : $($procMcp.Id))" -ForegroundColor Cyan }
} else {
    if ($Verbose) { Write-Host "🚀 Démarrage Server MCP dans une nouvelle fenêtre PowerShell..." -ForegroundColor Yellow }
    Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", "python server_mcp.py --name nova_middleware -f .env" -ErrorAction Stop
    if ($Verbose) { Write-Host "⏳ Pause de 5 secondes pour laisser MCP démarrer..." -ForegroundColor Yellow }
    Start-Sleep -Seconds 5
}

# Gestion de la configuration de Claude Desktop
$claudeConfigPath = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
if (Test-Path $claudeConfigPath) {
    if ($Verbose) { Write-Host "🔍 Lecture de la config Claude Desktop : $claudeConfigPath" -ForegroundColor Yellow }
    $cfg = Get-Content $claudeConfigPath | ConvertFrom-Json
    if ($cfg.integrations -and $cfg.integrations.nova_middleware) {
        if ($Verbose) { Write-Host "✔ Integration 'nova_middleware' déjà présente dans Claude Desktop" -ForegroundColor Green }
    } else {
        if ($Verbose) { Write-Host "⚙ Installation de 'nova_middleware' via MCP..." -ForegroundColor Yellow }
        mcp install nova_middleware --config "$claudeConfigPath"
        if ($Verbose) { Write-Host "✔ 'nova_middleware' ajouté à Claude Desktop" -ForegroundColor Green }
    }
} else {
    Write-Host "⚠ Fichier de config Claude Desktop introuvable : $claudeConfigPath" -ForegroundColor Magenta
    Write-Host "   Veuillez installer manuellement nova_middleware dans Claude Desktop." -ForegroundColor Magenta
}

# Récapitulatif final
Write-Host ""
Write-Host "🎯 Récapitulatif des services NOVA Middleware :" -ForegroundColor Cyan
Write-Host "-----------------------------------------------" -ForegroundColor Cyan
Write-Host "• FastAPI  : http://localhost:8000/" -ForegroundColor Green
Write-Host "• MCP      : nova_middleware" -ForegroundColor Green
Write-Host "• PostgreSQL : $env:DB_NAME@$env:DB_HOST" -ForegroundColor Green
Write-Host "-----------------------------------------------" -ForegroundColor Cyan
Write-Host "✨ Pour intégrer dans Claude Desktop :" -ForegroundColor Magenta
Write-Host "1. Redémarrez Claude Desktop si nécessaire." -ForegroundColor Magenta
Write-Host "2. Cliquez sur '+' et choisissez 'nova_middleware'." -ForegroundColor Magenta
Write-Host "3. Testez via la commande ping." -ForegroundColor Magenta