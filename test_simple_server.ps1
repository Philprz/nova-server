# test_simple_server.ps1
Write-Host "🔍 Test du serveur MCP simple..." -ForegroundColor Cyan
. .\venv\Scripts\Activate.ps1

Write-Host "📋 Exécution de 'mcp run simple_server.py'..." -ForegroundColor Yellow
mcp run simple_server.py