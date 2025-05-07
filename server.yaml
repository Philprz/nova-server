# fix_server_yaml.ps1
$serverYamlContent = @"
# -------------------------------
# server.yaml
# -------------------------------

name: nova_middleware
version: "1.0.0"

# Outils exposés au client MCP
capabilities:
  tools:
    - path: ./tools.py
    - path: ./services/exploration_salesforce.py
    - path: ./services/exploration_sap.py

# Transport utilisé (Claude Desktop = stdio)
transports:
  - type: stdio

heartbeat_interval: 30  # (optionnel, ping serveur toutes les 30 sec)
"@

$serverYamlContent | Out-File -FilePath "server.yaml" -Encoding utf8
Write-Host "Fichier server.yaml corrigé!" -ForegroundColor Green