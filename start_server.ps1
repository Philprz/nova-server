# start_server.ps1
# ======================================
# Script de démarrage sécurisé pour NOVA
# Vérifie l'environnement virtuel
# Lance Uvicorn avec logs détaillés
# ======================================

$logFile = "C:\Users\PPZ\NOVA\server_start.log"

Write-Output "--------------------------------------------------------"
Write-Output "Démarrage du serveur NOVA... ($(Get-Date))"
Write-Output "--------------------------------------------------------"
Start-Transcript -Path $logFile -Append

# Vérification de l'environnement virtuel
if (-not (Test-Path Env:VIRTUAL_ENV)) {
    Write-Error "❌ L'environnement virtuel n'est pas activé. Merci de faire 'venv\Scripts\Activate.ps1' avant de lancer ce script."
    Stop-Transcript
    exit 1
}

# Vérification que uvicorn est bien installé
if (-not (Get-Command uvicorn -ErrorAction SilentlyContinue)) {
    Write-Error "❌ Uvicorn n'est pas installé dans l'environnement virtuel. Exécutez 'pip install uvicorn[standard]' avant."
    Stop-Transcript
    exit 1
}

# Lancement du serveur
try {
    Write-Output "✅ Environnement détecté : $env:VIRTUAL_ENV"
    Write-Output "✅ Démarrage de l'API sur http://0.0.0.0:8000 ..."
    uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
}
catch {
    Write-Error "❌ Erreur lors du lancement du serveur : $_"
}
finally {
    Stop-Transcript
    Write-Output "--------------------------------------------------------"
    Write-Output "Fin du script ($(Get-Date))"
    Write-Output "--------------------------------------------------------"
}
