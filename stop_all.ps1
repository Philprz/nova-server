# stop_all.ps1
Write-Host "🛑 Arrêt des serveurs MCP et FastAPI..."

# Tuer FastAPI (uvicorn)
Get-Process -Name "uvicorn" -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "⛔ Fermeture de Uvicorn (PID $_.Id)..."
    Stop-Process -Id $_.Id -Force
}

# Tuer MCP (python)
Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -like "*server_mcp.py*"
} | ForEach-Object {
    Write-Host "⛔ Fermeture de MCP (PID $_.Id)..."
    Stop-Process -Id $_.Id -Force
}

Write-Host "✅ Tous les processus ciblés ont été arrêtés."
