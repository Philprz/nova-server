# install_mcp_simple.ps1
Write-Host "🔄 Activation de l'environnement virtuel..." -ForegroundColor Cyan
. .\venv\Scripts\Activate.ps1

# Verification de la commande MCP
if (-not (Get-Command "mcp" -ErrorAction SilentlyContinue)) {
    Write-Error "❌ MCP introuvable. Active l'environnement virtuel ou installe avec : pip install 'mcp[cli]'"
    exit 1
}

# Installation du serveur MCP
Write-Host "🚀 Installation du serveur MCP dans Claude Desktop..." -ForegroundColor Green
mcp install server_mcp.py --name "nova_middleware" -f .env

Write-Host "✅ Termine ! Redemarre Claude Desktop et clique sur ➕ > nova_middleware" -ForegroundColor Green