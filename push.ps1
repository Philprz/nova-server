# Script de sélection pour push Git
# Permet de choisir entre la version standard et la version IA

param(
    [Parameter(Mandatory=$false)]
    [switch]$AI,
    
    [Parameter(Mandatory=$false, ValueFromRemainingArguments=$true)]
    [string[]]$Arguments
)

Write-Host "=== NOVA POC - Sélecteur de Script Push ===" -ForegroundColor "Cyan"
Write-Host ""

if ($AI) {
    Write-Host "Utilisation de la version IA avancée..." -ForegroundColor "Green"
    Write-Host "Cette version génère des messages de commit très détaillés" -ForegroundColor "Gray"
    Write-Host ""
    
    # Vérifier si le script AI existe
    if (Test-Path ".\push_both_ai.ps1") {
        # Passer tous les arguments au script AI
        & .\push_both_ai.ps1 @Arguments
    }
    else {
        Write-Host "ERREUR: Le script push_both_ai.ps1 n'a pas été trouvé!" -ForegroundColor "Red"
        Write-Host "Assurez-vous que le fichier existe dans le répertoire courant." -ForegroundColor "Yellow"
        exit 1
    }
}
else {
    Write-Host "Utilisation de la version standard..." -ForegroundColor "Blue"
    Write-Host "Pour utiliser la version IA, ajoutez -AI" -ForegroundColor "Gray"
    Write-Host "Exemple: .\push.ps1 -AI" -ForegroundColor "DarkGray"
    Write-Host ""
    
    # Utiliser la version standard
    if (Test-Path ".\push_both.ps1") {
        # Passer tous les arguments au script standard
        & .\push_both.ps1 @Arguments
    }
    else {
        Write-Host "ERREUR: Le script push_both.ps1 n'a pas été trouvé!" -ForegroundColor "Red"
        Write-Host "Assurez-vous que le fichier existe dans le répertoire courant." -ForegroundColor "Yellow"
        exit 1
    }
}

# Si c'est la première utilisation, afficher les informations
if (-not (Test-Path ".push_selector_initialized")) {
    Write-Host "`n📚 GUIDE RAPIDE:" -ForegroundColor "Yellow"
    Write-Host "- Version standard : .\push.ps1 [""message""]" -ForegroundColor "Gray"
    Write-Host "- Version IA locale : .\push.ps1 -AI" -ForegroundColor "Gray"
    Write-Host "- Version IA OpenAI : .\push.ps1 -AI -UseAI -AIProvider OpenAI" -ForegroundColor "Gray"
    Write-Host "- Version IA Claude : .\push.ps1 -AI -UseAI -AIProvider Claude" -ForegroundColor "Gray"
    Write-Host "`nPour plus d'infos : voir GUIDE_PUSH_AI.md" -ForegroundColor "DarkGray"
    
    "" | Out-File -FilePath ".push_selector_initialized" -Force
}