# Script PowerShell simplifi� pour tester la syntaxe
param(
  [switch]$Verbose
)

# D�finir le r�pertoire du projet
$projectPath = "C:\Users\PPZ\NOVA"

# Fonction minimale pour tester la d�claration
function Test-Function {
    param (
        [string]$Message
    )
    
    Write-Host $Message
}

# Appel de fonction
Test-Function -Message "Ce script fonctionne correctement!"

# Affichage du succ�s
Write-Host "? Tout est OK!" -ForegroundColor Green