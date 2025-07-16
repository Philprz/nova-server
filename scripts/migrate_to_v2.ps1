# scripts/migrate_to_v2.ps1
# Script de migration vers l'architecture V2

param(
    [switch]$TestMode = $false,
    [switch]$BackupFirst = $true,
    [switch]$Verbose = $false
)

Write-Host "🚀 MIGRATION NOVA vers Architecture V2" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Green

# Configuration
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackupDir = Join-Path $ProjectRoot "backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
$LogFile = Join-Path $ProjectRoot "migration_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"

# Fonctions utilitaires
function Write-Log {
    param($Message, $Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "[$timestamp] [$Level] $Message"
    Write-Host $logEntry
    Add-Content -Path $LogFile -Value $logEntry
}

function Test-PythonModule {
    param($ModuleName)
    try {
        python -c "import $ModuleName"
        return $true
    } catch {
        return $false
    }
}

function Create-Directory {
    param($Path)
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
        Write-Log "📁 Dossier créé: $Path"
    }
}

function Backup-File {
    param($SourcePath, $BackupPath)
    if (Test-Path $SourcePath) {
        Copy-Item -Path $SourcePath -Destination $BackupPath -Force
        Write-Log "💾 Sauvegarde: $SourcePath -> $BackupPath"
    }
}

# Étape 1: Vérifications préliminaires
Write-Log "🔍 Étape 1: Vérifications préliminaires"

# Vérifier Python
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Log "❌ Python n'est pas installé ou pas dans le PATH" "ERROR"
    exit 1
}

# Vérifier les dépendances
$requiredModules = @("fastapi", "uvicorn", "pydantic", "asyncio")
foreach ($module in $requiredModules) {
    if (-not (Test-PythonModule $module)) {
        Write-Log "⚠️ Module Python manquant: $module" "WARNING"
    }
}

# Étape 2: Sauvegarde (si demandée)
if ($BackupFirst) {
    Write-Log "💾 Étape 2: Sauvegarde des fichiers existants"
    
    Create-Directory $BackupDir
    
    # Fichiers à sauvegarder
    $filesToBackup = @(
        "workflow/devis_workflow.py",
        "services/client_validator.py",
        "services/mcp_connector.py",
        "services/llm_extractor.py",
        "main.py"
    )
    
    foreach ($file in $filesToBackup) {
        $sourcePath = Join-Path $ProjectRoot $file
        $backupPath = Join-Path $BackupDir $file
        
        if (Test-Path $sourcePath) {
            $backupDir = Split-Path $backupPath
            Create-Directory $backupDir
            Backup-File $sourcePath $backupPath
        }
    }
    
    Write-Log "✅ Sauvegarde terminée dans: $BackupDir"
}

# Étape 3: Création de la structure V2
Write-Log "🏗️ Étape 3: Création de la structure de dossiers V2"

$dirsToCreate = @(
    "managers",
    "utils", 
    "models",
    "scripts",
    "tests/unit",
    "tests/integration"
)

foreach ($dir in $dirsToCreate) {
    Create-Directory (Join-Path $ProjectRoot $dir)
}

# Créer les fichiers __init__.py
$initDirs = @("managers", "utils", "models")
foreach ($dir in $initDirs) {
    $initFile = Join-Path $ProjectRoot "$dir/__init__.py"
    if (-not (Test-Path $initFile)) {
        "# $dir module" | Out-File -FilePath $initFile -Encoding UTF8
        Write-Log "📄 Créé: $initFile"
    }
}

# Étape 4: Installation des nouveaux fichiers (simulation en mode test)
Write-Log "📦 Étape 4: Installation des nouveaux fichiers"

if ($TestMode) {
    Write-Log "🧪 MODE TEST: Simulation de l'installation des fichiers"
    
    $newFiles = @(
        "managers/client_manager.py",
        "managers/product_manager.py", 
        "managers/quote_manager.py",
        "utils/common_utils.py",
        "models/data_models.py",
        "workflow/devis_workflow_v2.py"
    )
    
    foreach ($file in $newFiles) {
        Write-Log "  📄 [SIMULATION] Installerait: $file"
    }
} else {
    Write-Log "📥 Veuillez maintenant copier les fichiers fournis dans les dossiers appropriés:"
    Write-Log "  - managers/client_manager.py"
    Write-Log "  - managers/product_manager.py"
    Write-Log "  - managers/quote_manager.py"
    Write-Log "  - utils/common_utils.py"
    Write-Log "  - models/data_models.py"
    Write-Log "  - workflow/devis_workflow_v2.py"
    
    Read-Host "Appuyez sur Entrée quand les fichiers sont copiés..."
}

# Étape 5: Modification du main.py pour supporter V2
Write-Log "🔧 Étape 5: Modification du main.py"

$mainPyPath = Join-Path $ProjectRoot "main.py"
if (Test-Path $mainPyPath) {
    # Backup du main.py original
    $mainBackup = Join-Path $BackupDir "main.py.backup"
    Backup-File $mainPyPath $mainBackup
    
    # Ajouter l'import V2 (simulation)
    if ($TestMode) {
        Write-Log "🧪 [SIMULATION] Ajouterait l'import DevisWorkflowV2 dans main.py"
    } else {
        Write-Log "✏️ Ajout de l'import V2 dans main.py"
        
        # Ligne à ajouter
        $importLine = "from workflow.devis_workflow_v2 import DevisWorkflowV2"
        
        # Lire le contenu actuel
        $content = Get-Content $mainPyPath
        
        # Ajouter l'import après les autres imports
        $newContent = @()
        $importAdded = $false
        
        foreach ($line in $content) {
            $newContent += $line
            if ($line.StartsWith("from workflow.devis_workflow import DevisWorkflow") -and -not $importAdded) {
                $newContent += $importLine
                $importAdded = $true
                Write-Log "  ✅ Import V2 ajouté"
            }
        }
        
        # Sauvegarder le fichier modifié
        $newContent | Out-File -FilePath $mainPyPath -Encoding UTF8
    }
}

# Étape 6: Création des routes V2
Write-Log "🛣️ Étape 6: Création des routes V2"

$routeV2Content = @"
# Route V2 pour test parallèle
@app.post("/api/v2/generate_quote")
async def generate_quote_v2(request: dict):
    try:
        workflow_v2 = DevisWorkflowV2(draft_mode=request.get("draft_mode", False))
        result = await workflow_v2.process_quote_request(request.get("prompt", ""))
        return result
    except Exception as e:
        return {"success": False, "error": str(e), "version": "v2"}

@app.get("/api/v2/status")
async def status_v2():
    return {
        "version": "v2",
        "status": "operational",
        "architecture": "modular",
        "timestamp": datetime.now().isoformat()
    }
"@

if ($TestMode) {
    Write-Log "🧪 [SIMULATION] Ajouterait les routes V2 dans main.py"
} else {
    Write-Log "📝 Ajout des routes V2 (à faire manuellement)"
    Write-Log "  Ajoutez ce code dans main.py:"
    Write-Log $routeV2Content
}

# Étape 7: Tests de validation
Write-Log "🧪 Étape 7: Tests de validation"

if (-not $TestMode) {
    Write-Log "🔍 Lancement des tests de validation..."
    
    # Test d'import
    try {
        python -c "from managers.client_manager import ClientManager; print('✅ ClientManager importé')"
        Write-Log "✅ ClientManager: Import OK"
    } catch {
        Write-Log "❌ ClientManager: Erreur d'import" "ERROR"
    }
    
    try {
        python -c "from managers.product_manager import ProductManager; print('✅ ProductManager importé')"
        Write-Log "✅ ProductManager: Import OK"
    } catch {
        Write-Log "❌ ProductManager: Erreur d'import" "ERROR"
    }
    
    try {
        python -c "from managers.quote_manager import QuoteManager; print('✅ QuoteManager importé')"
        Write-Log "✅ QuoteManager: Import OK"
    } catch {
        Write-Log "❌ QuoteManager: Erreur d'import" "ERROR"
    }
    
    try {
        python -c "from utils.common_utils import ResponseBuilder; print('✅ Utils importés')"
        Write-Log "✅ Utils: Import OK"
    } catch {
        Write-Log "❌ Utils: Erreur d'import" "ERROR"
    }
    
    try {
        python -c "from models.data_models import ClientData; print('✅ Models importés')"
        Write-Log "✅ Models: Import OK"
    } catch {
        Write-Log "❌ Models: Erreur d'import" "ERROR"
    }
}

# Étape 8: Instructions post-migration
Write-Log "📋 Étape 8: Instructions post-migration"

Write-Host ""
Write-Host "🎉 MIGRATION TERMINÉE!" -ForegroundColor Green
Write-Host ""
Write-Host "📋 PROCHAINES ÉTAPES:" -ForegroundColor Yellow
Write-Host "1. Tester l'API V2: http://localhost:8000/api/v2/status"
Write-Host "2. Comparer les performances V1 vs V2"
Write-Host "3. Migrer les routes une par une"
Write-Host "4. Surveiller les logs: $LogFile"
Write-Host ""
Write-Host "🔄 ROLLBACK si nécessaire:" -ForegroundColor Red
Write-Host "   Restaurer depuis: $BackupDir"
Write-Host ""
Write-Host "📊 MONITORING:" -ForegroundColor Cyan
Write-Host "   - Cache V2: /api/v2/cache-stats"
Write-Host "   - Performance: /api/v2/metrics"
Write-Host "   - Santé: /api/v2/health"

Write-Log "🏁 Migration terminée avec succès!"
Write-Log "📂 Logs disponibles dans: $LogFile"
Write-Log "💾 Sauvegarde disponible dans: $BackupDir"

# Optionnel: Ouvrir le dossier de sauvegarde
if ($BackupFirst -and -not $TestMode) {
    $openBackup = Read-Host "Ouvrir le dossier de sauvegarde? (y/n)"
    if ($openBackup -eq "y") {
        Start-Process $BackupDir
    }
}