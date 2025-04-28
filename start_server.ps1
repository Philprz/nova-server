# -----------------------------------------
# start_server.ps1
# Script pour démarrer MCP Nova Middleware
# -----------------------------------------

# Se placer dans le dossier du projet
Set-Location -Path "C:\Users\PPZ\NOVA"

# Activer l'environnement virtuel
& "C:\Users\PPZ\NOVA\venv\Scripts\Activate.ps1"

# Démarrer le serveur MCP
python server_mcp.py
