# -------------------------------
# start_server.ps1 - Version corrigee
# -------------------------------
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# (1) Aller dans le dossier projet
Write-Host "Changement de repertoire vers C:\Users\PPZ\NOVA"
Set-Location "C:\Users\PPZ\NOVA"

# (2) Activer l'environnement virtuel (venv attendu dans ./venv)
if (Test-Path ".\venv\Scripts\Activate.ps1") {
    Write-Host "Activation de l'environnement virtuel..."
    .\venv\Scripts\Activate.ps1
} else {
    Write-Host "Aucun environnement virtuel trouve (./venv)."
    Write-Host "MCP sera lance avec l'environnement Python global."
}

# (3) Verification presence de MCP SDK
try {
    pip show mcp | Out-Null
    Write-Host "MCP SDK detecte."
} catch {
    Write-Host "MCP CLI ou SDK non installe. Execute : pip install 'mcp[cli]'"
    Pause
    exit
}
# (4) Réenregistrement MCP avec le bon interpréteur Python virtuel
Write-Host "Reenregistrement du serveur MCP avec le bon environnement..."
mcp install server_mcp.py --name "nova_middleware" --python "C:/Users/PPZ/NOVA/venv/Scripts/python.exe"

# (5) Lancer le serveur MCP Python
Write-Host "Lancement du serveur MCP (server_mcp.py)..."
python server_mcp.py
Write-Host "MCP Server 'nova_middleware' demarre (transport: stdio)"

# (6) Fin du script
Write-Host "Le serveur MCP s'est arrêté ou a été fermé manuellement."
Pause
