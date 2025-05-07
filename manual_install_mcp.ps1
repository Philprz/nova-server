# manual_install_mcp.ps1
$claudeMCPDir = "$env:APPDATA\Claude\mcp_servers\nova_middleware"

# Créer le dossier du serveur MCP
if (-not (Test-Path $claudeMCPDir)) {
    New-Item -Path $claudeMCPDir -ItemType Directory -Force
}

# Copier les fichiers nécessaires
Copy-Item -Path "server_mcp.py" -Destination "$claudeMCPDir\server_mcp.py" -Force
Copy-Item -Path "mcp_app.py" -Destination "$claudeMCPDir\mcp_app.py" -Force
Copy-Item -Path "tools.py" -Destination "$claudeMCPDir\tools.py" -Force
Copy-Item -Path "server.yaml" -Destination "$claudeMCPDir\server.yaml" -Force

# Créer un dossier services et copier les fichiers d'exploration
$servicesDir = "$claudeMCPDir\services"
if (-not (Test-Path $servicesDir)) {
    New-Item -Path $servicesDir -ItemType Directory -Force
}
Copy-Item -Path "services\exploration_salesforce.py" -Destination "$servicesDir\exploration_salesforce.py" -Force
Copy-Item -Path "services\exploration_sap.py" -Destination "$servicesDir\exploration_sap.py" -Force
Copy-Item -Path "services\__init__.py" -Destination "$servicesDir\__init__.py" -Force

Write-Host "✅ Serveur MCP installé manuellement à : $claudeMCPDir"
Write-Host "🔄 Redémarrez Claude Desktop et sélectionnez 'nova_middleware' dans le menu des serveurs MCP"