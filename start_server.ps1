# start_server.ps1
# ======================================
# Script de démarrage sécurisé pour NOVA
# Sans sortie standard pour compatibilité MCP (Claude)
# Logs détaillés uniquement dans server_start.log
# ======================================

$logFile = "C:\Users\PPZ\NOVA\server_start.log"

# Démarrage de la transcription (tout ira dans le fichier log)
Start-Transcript -Path $logFile -Append

try {
    # Vérification de l'environnement virtuel
    if (-not (Test-Path Env:VIRTUAL_ENV)) {
        Write-Error "❌ L'environnement virtuel n'est pas activé. Merci de faire 'venv\Scripts\Activate.ps1' avant de lancer ce script."
        exit 1
    }

    # Vérification que uvicorn est installé
    if (-not (Get-Command uvicorn -ErrorAction SilentlyContinue)) {
        Write-Error "❌ Uvicorn n'est pas installé dans l'environnement virtuel. Exécutez 'pip install uvicorn[standard]' avant."
        exit 1
    }

    # Lancement du serveur FastAPI
    uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

} catch {
    Write-Error "❌ Erreur lors du lancement du serveur : $_"
    exit 1
} finally {
    Stop-Transcript
}
