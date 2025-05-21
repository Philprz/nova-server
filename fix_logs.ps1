# Créer un nouveau fichier fix_logs.ps1

# Configuration de l'encodage pour les logs
$LogsPath = "logs/workflow_devis.log"

# Créer le dossier logs s'il n'existe pas
if (-not (Test-Path "logs")) {
    New-Item -ItemType Directory -Path "logs" | Out-Null
}

# Créer ou remplacer le contenu du fichier de logs
Out-File -FilePath $LogsPath -Encoding utf8 -Force

# Créer un fichier Python temporaire avec la configuration de logging
$pythonConfigContent = @"
import sys
import io
import os
import logging

# Configuration de l'encodage des flux standard
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Création du dossier logs si nécessaire
os.makedirs('logs', exist_ok=True)

# Configuration des logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='logs/workflow_devis.log',
    encoding='utf-8'
)
logger = logging.getLogger("workflow_devis")
logger.info("Démarrage du workflow de devis")
"@

# Écrire la configuration Python dans un fichier temporaire
$pythonTempFile = "temp_logging_config.py"
Set-Content -Path $pythonTempFile -Value $pythonConfigContent -Encoding UTF8

# Exécuter le fichier Python temporaire pour tester la configuration
Write-Host "Test de la configuration de logging..."
python $pythonTempFile

# Nettoyer le fichier temporaire
if (Test-Path $pythonTempFile) {
    Remove-Item $pythonTempFile
}

Write-Host "Configuration de logging terminée. Fichier logs créé à $LogsPath"