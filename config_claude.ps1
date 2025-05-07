# config_claude.ps1
# Chemin vers le fichier de configuration Claude
$configPath = "$env:APPDATA\Claude\claude-settings.json"
$configDir = Split-Path -Path $configPath -Parent

# Créer le dossier si nécessaire
if (-not (Test-Path $configDir)) {
    New-Item -Path $configDir -ItemType Directory -Force
}

# Contenu de la configuration
$configContent = @"
{
  "mcpServers": {
    "nova_middleware": {
      "command": "python",
      "args": [
        "C:\\Users\\PPZ\\NOVA\\simple_server.py"
      ],
      "env": {
        "API_KEY": "ITS2025",
        "SAP_REST_BASE_URL": "https://51.91.130.136:50000/b1s/v1",
        "SAP_USER": "manager",
        "SAP_CLIENT_PASSWORD": "Tirips44!",
        "SAP_CLIENT": "SBODemoFR",
        "SALESFORCE_USERNAME": "p.perez-gt8k@force.com",
        "SALESFORCE_PASSWORD": "Ae@s5GfCic?3EtNq",
        "SALESFORCE_SECURITY_TOKEN": "0RLKx2DTvjrMj2eulLgG5ge1i",
        "SALESFORCE_DOMAIN": "login"
      }
    }
  }
}
"@

$configContent | Out-File -FilePath $configPath -Encoding utf8 -Force
Write-Host "✅ Configuration Claude Desktop créée à : $configPath"