# setup-clause-config.ps1
Copy-Item .\claude_desktop_config.json.template .\claude_desktop_config.json -Force
# (optionnel) mettez-le en lecture seule pour éviter toute écriture ultérieure
attrib +r .\claude_desktop_config.json
