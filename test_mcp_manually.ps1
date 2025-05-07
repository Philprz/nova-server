# test_mcp_manually.ps1
Write-Host "🔍 Test du serveur MCP manuellement..." -ForegroundColor Cyan
. .\venv\Scripts\Activate.ps1

Write-Host "📋 Exécution de 'mcp run server_mcp.py'..." -ForegroundColor Yellow
mcp run server_mcp.py