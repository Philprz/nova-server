# Créer un nouveau fichier fix_logs.ps1

# Configuration de l'encodage pour les logs
$LogsPath = "logs/workflow_devis.log"

# Créer le dossier logs s'il n'existe pas
if (-not (Test-Path "logs")) {
    New-Item -ItemType Directory -Path "logs" | Out-Null
}

# Ajouter ceci au début de workflow/devis_workflow.py
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Configuration des logs
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='logs/workflow_devis.log',
    encoding='utf-8'  # Spécifier l'encodage UTF-8
)
logger = logging.getLogger("workflow_devis")