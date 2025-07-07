# Script pour vérifier et corriger la configuration des remotes Git
Write-Host "=== VÉRIFICATION DE LA CONFIGURATION GIT ===" -ForegroundColor "Cyan"
Write-Host ""

# Vérifier la configuration actuelle des remotes
Write-Host "Configuration actuelle des remotes :" -ForegroundColor "Yellow"
$remotes = git remote -v

if ($remotes) {
    $remotes | ForEach-Object { Write-Host $_ }
} else {
    Write-Host "Aucun remote configuré" -ForegroundColor "Red"
}

Write-Host ""
Write-Host "Configuration attendue :" -ForegroundColor "Green"
Write-Host "origin    : https://github.com/Philprz/nova-server.git"
Write-Host "secondary : https://github.com/www-it-spirit-com/NOVAPOC.git"

Write-Host ""
Write-Host "Voulez-vous configurer automatiquement les remotes corrects ? (O/n)" -ForegroundColor "Yellow"
$response = Read-Host

if ($response -eq "" -or $response -eq "O" -or $response -eq "o") {
    # Vérifier et configurer origin
    $originUrl = git remote get-url origin 2>$null
    if ($originUrl -ne "https://github.com/Philprz/nova-server.git") {
        if ($originUrl) {
            Write-Host "Mise à jour de l'URL origin..." -ForegroundColor "Yellow"
            git remote set-url origin https://github.com/Philprz/nova-server.git
        } else {
            Write-Host "Ajout du remote origin..." -ForegroundColor "Yellow"
            git remote add origin https://github.com/Philprz/nova-server.git
        }
        Write-Host "Remote origin configuré correctement" -ForegroundColor "Green"
    } else {
        Write-Host "Remote origin déjà configuré correctement" -ForegroundColor "Green"
    }

    # Vérifier et configurer secondary
    $secondaryUrl = git remote get-url secondary 2>$null
    if ($secondaryUrl -ne "https://github.com/www-it-spirit-com/NOVAPOC.git") {
        if ($secondaryUrl) {
            Write-Host "Mise à jour de l'URL secondary..." -ForegroundColor "Yellow"
            git remote set-url secondary https://github.com/www-it-spirit-com/NOVAPOC.git
        } else {
            Write-Host "Ajout du remote secondary..." -ForegroundColor "Yellow"
            git remote add secondary https://github.com/www-it-spirit-com/NOVAPOC.git
        }
        Write-Host "Remote secondary configuré correctement" -ForegroundColor "Green"
    } else {
        Write-Host "Remote secondary déjà configuré correctement" -ForegroundColor "Green"
    }

    Write-Host ""
    Write-Host "Configuration finale :" -ForegroundColor "Green"
    git remote -v
} else {
    Write-Host "Configuration annulée" -ForegroundColor "Yellow"
}