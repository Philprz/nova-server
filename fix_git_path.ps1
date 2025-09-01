# Script pour ajouter Git au PATH temporairement
$gitPath = "C:\Program Files\Git\bin"
if (Test-Path $gitPath) {
    $env:PATH = "$gitPath;$env:PATH"
    Write-Host "Git ajouté au PATH temporairement" -ForegroundColor Green
    Write-Host "Vous pouvez maintenant utiliser Git dans cette session PowerShell"
    
    # Tester si Git fonctionne
    Write-Host "`nTest de Git:" -ForegroundColor Yellow
    git --version
} else {
    Write-Host "Git n'est pas installé dans le répertoire par défaut" -ForegroundColor Red
}