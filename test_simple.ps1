# Script PowerShell simplifié pour tester la syntaxe
param(
  [switch]$Verbose
)

# Définir le répertoire du projet
$projectPath = "C:\Users\PPZ\NOVA"

# Fonction minimale pour tester la déclaration
function Test-Function {
    param (
        [string]$Message
    )
    
    Write-Host $Message
}

# Appel de fonction
Test-Function -Message "Ce script fonctionne correctement!"

# Affichage du succès
Write-Host "? Tout est OK!" -ForegroundColor Green