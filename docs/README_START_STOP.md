==============================================
🚀 Guide de démarrage et arrêt du serveur NOVA
==============================================

# 📁 Dossier projet :
C:\Users\PPZ\NOVA

# 🛠 Scripts disponibles :

1️⃣ start_server.bat
   ➔ Démarre le serveur MCP NOVA en utilisant start_server.ps1.
   ➔ Ouvre une fenêtre PowerShell dédiée pour afficher les logs.
   ➔ Utilise MCP CLI pour charger le fichier server.yaml.

2️⃣ stop_server.bat
   ➔ Arrête uniquement le serveur MCP lié à start_server.ps1.
   ➔ N'affecte PAS les autres fenêtres PowerShell ouvertes.
   ➔ Tue proprement le processus correspondant.

3️⃣ restart_server.bat
   ➔ Arrête le serveur MCP s'il est actif.
   ➔ Attend quelques secondes.
   ➔ Redémarre automatiquement dans une nouvelle fenêtre.

# 🔥 Utilisation rapide :

- Pour DÉMARRER : double-cliquez sur start_server.bat
- Pour ARRÊTER : double-cliquez sur stop_server.bat
- Pour REDÉMARRER : double-cliquez sur restart_server.bat

# 🛑 Attention :

- Les scripts utilisent -ExecutionPolicy Bypass (autorisation temporaire pour exécuter start_server.ps1).
- Si vous déplacez le dossier NOVA, pensez à **mettre à jour** les chemins dans les scripts .bat.

# 📋 Note :

- Votre server.yaml contient la configuration officielle du serveur MCP (nom, outils, transport).
- Votre tools.py contient vos outils enregistrés : Salesforce (query) et SAP (read).

# ✅ Prêt à l'emploi !
