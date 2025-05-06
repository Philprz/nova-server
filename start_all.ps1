# start_all.ps1
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force

Write-Host "🔄 Activation de l'environnement virtuel..."
. .\venv\Scripts\Activate.ps1

# Vérifications de dépendances
if (-not (Get-Command "mcp" -ErrorAction SilentlyContinue)) {
    Write-Error "❌ MCP introuvable. Active l'environnement ou installe-le avec pip install 'mcp[cli]'"
    exit 1
}

if (-not (Get-Command "uvicorn" -ErrorAction SilentlyContinue)) {
    Write-Error "❌ Uvicorn introuvable. Lance : pip install -r requirements.txt"
    exit 1
}

# Lancer le serveur MCP dans une nouvelle console
Start-Process powershell -ArgumentList "-NoExit", "-Command", "mcp run server_mcp.py"

# Lancer FastAPI dans une autre console
Start-Process powershell -ArgumentList "-NoExit", "-Command", "uvicorn main:app --reload"

Write-Host "✅ Les serveurs MCP et FastAPI sont lancés dans deux consoles distinctes."
