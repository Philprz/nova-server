# Script pour push sur les deux repositories NOVA POC (VERSION COMPLÈTE)
# Usage: .\push_both_with_secondary.ps1 ["Message de commit"]
# Si aucun message n'est fourni, le script demandera interactivement

param(
    [Parameter(Mandatory=$false)]
    [string]$CommitMessage = ""
)

Write-Host "=== PUSH DUAL REPOSITORY NOVA POC (VERSION COMPLÈTE) ===" -ForegroundColor "Cyan"
Write-Host ""

# Vérifier s'il y a des changements
$status = git status --porcelain
if ($status) {
    Write-Host "Changements détectés, ajout et commit..." -ForegroundColor "Yellow"
    
    # Si aucun message de commit n'est fourni, demander interactivement
    if ([string]::IsNullOrEmpty($CommitMessage)) {
        $CommitMessage = Read-Host "Entrez votre message de commit"
    }
    
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
$pushResult = git push origin main 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "Push réussi vers repository principal" -ForegroundColor "Green"
} else {
    Write-Host "Erreur lors du push vers repository principal:" -ForegroundColor "Red"
    Write-Host "$pushResult" -ForegroundColor "Red"
    exit 1
}

Write-Host ""

# Push vers repository secondaire (personnel)
Write-Host "Push vers repository secondaire (nova-poc-commercial)..." -ForegroundColor "Blue"

# Ajouter le remote secondaire s'il n'existe pas
$remotes = git remote
if ($remotes -notcontains "secondary") {
    git remote add secondary https://github.com/Symple44/nova-poc-commercial.git
    Write-Host "Remote secondaire ajouté" -ForegroundColor "Yellow"
}

# Vérifier d'abord si le repository existe
Write-Host "Vérification de l'existence du repository secondaire..." -ForegroundColor "Yellow"
$repoCheck = git ls-remote https://github.com/Symple44/nova-poc-commercial.git 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ATTENTION: Le repository secondaire 'nova-poc-commercial' n'existe pas sur GitHub" -ForegroundColor "Red"
    Write-Host "Erreur: $repoCheck" -ForegroundColor "Red"
    Write-Host "Veuillez créer le repository sur GitHub ou corriger l'URL" -ForegroundColor "Yellow"
    Write-Host "Le push vers le repository principal a réussi" -ForegroundColor "Green"
} else {
    # Le repository existe, procéder au push
    $pushSecondaryResult = git push secondary main 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Push réussi vers repository secondaire" -ForegroundColor "Blue"
    } else {
        Write-Host "Erreur lors du push vers repository secondaire:" -ForegroundColor "Red"
        Write-Host "$pushSecondaryResult" -ForegroundColor "Red"
        Write-Host "Le push vers le repository principal a réussi, mais pas vers le secondaire" -ForegroundColor "Yellow"
    }
}

Write-Host ""
Write-Host "=== PUSH TERMINÉ ===" -ForegroundColor "Cyan"