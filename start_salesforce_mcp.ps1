# start_salesforce_mcp.ps1
$ErrorActionPreference = "Stop"
$projectDir = "C:\Users\PPZ\NOVA"
Set-Location $projectDir

# Activer l'environnement virtuel
Write-Host "Activation de l'environnement virtuel..." -ForegroundColor Yellow
try {
    & "$projectDir\venv\Scripts\Activate.ps1"
} catch {
    Write-Host "Erreur lors de l'activation de l'environnement: $_" -ForegroundColor Red
    exit 1
}

# Installer explicitement simple-salesforce
Write-Host "Installation de simple-salesforce..." -ForegroundColor Yellow
try {
    pip install simple-salesforce --upgrade --no-cache-dir
    pip install python-dotenv
} catch {
    Write-Host "Erreur lors de l'installation: $_" -ForegroundColor Red
    exit 1
}

# Vérifier que le module est bien installé
Write-Host "Vérification de l'installation..." -ForegroundColor Yellow
try {
    python -c "import simple_salesforce; print('✅ simple-salesforce version:', simple_salesforce.__version__)"
} catch {
    Write-Host "Erreur lors de la vérification: $_" -ForegroundColor Red
    exit 1
}

# Lancer le serveur MCP
Write-Host "Démarrage du serveur MCP Salesforce..." -ForegroundColor Green
python salesforce_mcp_minimal.py