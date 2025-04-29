# -------------------------------
# start_server.ps1
# -------------------------------

# (1) Aller dans le bon dossier projet
Write-Host "📁 Changement de répertoire vers C:\Users\PPZ\NOVA"
Set-Location "C:\Users\PPZ\NOVA"

# (2) Activer l'environnement virtuel s'il existe (optionnel mais conseillé)
if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    Write-Host "🐍 Activation de l'environnement virtuel..."
    .\.venv\Scripts\Activate.ps1
} else {
    Write-Host "⚠️ Aucun environnement virtuel trouvé (.venv)."
    Write-Host "⚠️ MCP sera lancé avec l'environnement Python global."
}

# (3) Vérifier que la commande MCP est disponible
try {
    mcp --version
} catch {
    Write-Host "❌ MCP CLI n'est pas installé. Exécute : pip install 'mcp[cli]'"
    exit
}

# (4) Lancer le serveur MCP
Write-Host "🚀 Lancement du serveur MCP..."
mcp server serve --config server.yaml

# (5) Garder la fenêtre ouverte après l'arrêt
Write-Host "🏁 Serveur arrêté. Appuyez sur une touche pour fermer."
Pause
