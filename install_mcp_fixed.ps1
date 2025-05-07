# install_mcp_fixed.ps1
Write-Host "🔄 Activation de l'environnement virtuel..." -ForegroundColor Cyan
. .\venv\Scripts\Activate.ps1

# Vérification de la commande MCP
if (-not (Get-Command "mcp" -ErrorAction SilentlyContinue)) {
    Write-Error "❌ MCP introuvable. Active l'environnement virtuel ou installe avec : pip install 'mcp[cli]'"
    exit 1
}

# Suppression de l'ancienne installation si elle existe
Write-Host "🧹 Nettoyage d'une éventuelle installation existante..." -ForegroundColor Yellow
mcp uninstall nova_middleware -y

# Installation du serveur
Write-Host "🚀 Installation du serveur MCP dans Claude Desktop..." -ForegroundColor Green
mcp install server_mcp.py --name "nova_middleware" -f .env

Write-Host "✅ Terminé ! Redémarre Claude Desktop et clique sur ➕ > nova_middleware" -ForegroundColor Green