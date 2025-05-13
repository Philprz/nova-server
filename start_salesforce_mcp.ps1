# start_salesforce_mcp.ps1
$projectDir = "C:\Users\PPZ\NOVA"
Set-Location $projectDir

# Activer l'environnement virtuel et installer explicitement simple-salesforce
& "$projectDir\venv\Scripts\Activate.ps1"
pip install simple-salesforce
