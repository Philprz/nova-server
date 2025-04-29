# start_server_debug.ps1 - version stable
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# Aller dans le dossier du projet
Set-Location "C:\Users\PPZ\NOVA"

# Activer l'environnement virtuel
if (Test-Path ".\venv\Scripts\Activate.ps1") {
    .\venv\Scripts\Activate.ps1
} elseif (Test-Path ".\.venv\Scripts\Activate.ps1") {
    .\.venv\Scripts\Activate.ps1
} else {
    Write-Host "Pas d'environnement virtuel détecté."
}

# Vérifier MCP
try {
    pip show mcp | Out-Null
} catch {
    Write-Host "MCP manquant. Exécute : pip install mcp[cli]"
    Pause
    exit
}

# Lancer FastAPI REST (main.py) dans une nouvelle console
Write-Host "Lancement REST API (main.py)..."
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-NoProfile",
    "-ExecutionPolicy Bypass",
    "-Command",
    "cd 'C:\Users\PPZ\NOVA'; ./venv/Scripts/Activate.ps1; python main.py"
)

# Lancer MCP Inspector (mcp dev server_mcp.py)
Write-Host "🟢 Lancement MCP Inspector..."
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-NoProfile",
    "-ExecutionPolicy Bypass",
    "-Command",
    "cd 'C:\Users\PPZ\NOVA'; ./venv/Scripts/Activate.ps1; mcp dev server_mcp.py"
)

# Lancer serveur Claude Desktop en STDIO (serveur MCP officiel)
Write-Host "Serveur Claude (server_mcp.py)..."
python server_mcp.py

Pause
