Start-Transcript -Path "C:\Users\PPZ\NOVA\nova\server_start.log" -Append

try {
    Write-Output "[$(Get-Date)] Lancement du serveur NOVA..."
    
    # Aller dans le dossier du projet
    Set-Location "C:\Users\PPZ\NOVA\nova"

    # Activer l'environnement virtuel si besoin
    if (Test-Path ".\venv\Scripts\Activate.ps1") {
        . .\venv\Scripts\Activate.ps1
    }

    # Lancer le serveur
    uvicorn backend:main:app --host 0.0.0.0 --port 8000
}
catch {
    Write-Error "Erreur lors du lancement du serveur : $_"
}
finally {
    Stop-Transcript
}
