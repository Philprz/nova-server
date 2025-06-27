# Script pour push sur les deux repositories NOVA POC
# Usage: .\push_both.ps1 "Message de commit"

param(
    [Parameter(Mandatory=$false)]
    [string]$CommitMessage = "Update POC NOVA"
)

Write-Host "=== PUSH DUAL REPOSITORY NOVA POC ===" -ForegroundColor "Cyan"
Write-Host ""

# Vérifier s'il y a des changements
$status = git status --porcelain
if ($status) {
    Write-Host "Changements détectés, ajout et commit..." -ForegroundColor "Yellow"
    
    # Ajouter tous les fichiers
    git add .
    
    # Commiter avec le message fourni
    git commit -m $CommitMessage
    
    Write-Host "Commit créé: $CommitMessage" -ForegroundColor "Green"
} else {
    Write-Host "Aucun changement à commiter" -ForegroundColor "Gray"
}

Write-Host ""

# Push vers repository principal (entreprise)
Write-Host "Push vers repository principal (www-it-spirit-com)..." -ForegroundColor "Green"
try {
    git push origin main
    Write-Host "✅ Push réussi vers repository principal" -ForegroundColor "Green"
} catch {
    Write-Host "❌ Erreur push repository principal: $_" -ForegroundColor "Red"
}

Write-Host ""

# Push vers repository personnel
Write-Host "Push vers repository personnel (Philprz)..." -ForegroundColor "Yellow"
try {
    git push personal main  
    Write-Host "✅ Push réussi vers repository personnel" -ForegroundColor "Green"
} catch {
    Write-Host "❌ Erreur push repository personnel: $_" -ForegroundColor "Red"
}

Write-Host ""
Write-Host "=== PUSH TERMINÉ SUR LES DEUX REPOSITORIES ===" -ForegroundColor "Cyan"

# Afficher le statut final
git status --short