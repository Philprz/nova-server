# start_nova_simple.ps1
param (
    [switch]$NoLogs
)

$projectDir = "C:\Users\PPZ\NOVA"
Set-Location $projectDir

# Activer l'environnement virtuel
& "$projectDir\venv\Scripts\Activate.ps1"

# Fonction pour démarrer un processus
function Start-NovaProcess {
    param (
        [string]$Name,
        [string]$Command,
        [string]$Arguments
    )
    
    if (-not $NoLogs) {
        Write-Host "Démarrage de $Name..." -ForegroundColor Yellow
    }
    
    Start-Process -NoNewWindow -FilePath $Command -ArgumentList $Arguments
    
    if (-not $NoLogs) {
        Write-Host "$Name démarré" -ForegroundColor Green
    }
}

# Démarrer FastAPI
Start-NovaProcess -Name "FastAPI" -Command "python" -Arguments "-m uvicorn main:app --reload"

# Démarrer les serveurs MCP
Start-NovaProcess -Name "MCP Salesforce" -Command "python" -Arguments "salesforce_mcp_minimal.py"
Start-NovaProcess -Name "MCP SAP" -Command "python" -Arguments "sap_mcp_minimal.py"

if (-not $NoLogs) {
    Write-Host "`nTous les services NOVA sont démarrés" -ForegroundColor Cyan
    Write-Host "- FastAPI: http://localhost:8000/" -ForegroundColor Cyan
    Write-Host "- MCP Salesforce: configuré dans Claude Desktop" -ForegroundColor Cyan
    Write-Host "- MCP SAP: configuré dans Claude Desktop" -ForegroundColor Cyan
}