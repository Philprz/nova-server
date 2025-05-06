# install_mcp.ps1
Write-Host "🔄 Activation de l'environnement virtuel..."
. .\venv\Scripts\Activate.ps1

# Vérification de la commande MCP
if (-not (Get-Command "mcp" -ErrorAction SilentlyContinue)) {
    Write-Error "❌ MCP introuvable. Active l'environnement virtuel ou installe avec : pip install 'mcp[cli]'"
    exit 1
}

Write-Host "🚀 Installation du serveur MCP dans Claude Desktop..."
mcp install server_mcp.py --name "nova_middleware" -f .env

Write-Host "✅ Terminé ! Redémarre Claude Desktop et clique sur ➕ > nova_middleware"
