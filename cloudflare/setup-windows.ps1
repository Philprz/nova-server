# Script PowerShell pour configurer NOVA Backend comme service Windows
# Utilise NSSM (Non-Sucking Service Manager)

param(
    [string]$NovaPath = "C:\Users\PPZ\NOVA-SERVER",
    [string]$ServiceName = "NOVA-Backend"
)

# Couleurs
function Write-Success { param($msg) Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Error { param($msg) Write-Host "[ERREUR] $msg" -ForegroundColor Red }
function Write-Info { param($msg) Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Warning { param($msg) Write-Host "[ATTENTION] $msg" -ForegroundColor Yellow }

Write-Host ""
Write-Host "=========================================="
Write-Host "  Configuration NOVA Backend"
Write-Host "  Service Windows avec NSSM"
Write-Host "=========================================="
Write-Host ""

# Vérifier droits admin
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "Ce script doit être exécuté en tant qu'administrateur"
    Write-Info "Clic droit sur PowerShell → Exécuter en tant qu'administrateur"
    exit 1
}

Write-Success "Exécution en administrateur"

# Vérifier que NOVA existe
if (-not (Test-Path $NovaPath)) {
    Write-Error "Dossier NOVA introuvable : $NovaPath"
    exit 1
}

Write-Success "Dossier NOVA trouvé : $NovaPath"

# Vérifier que Python existe
$pythonPath = Join-Path $NovaPath ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonPath)) {
    Write-Error "Python introuvable : $pythonPath"
    Write-Info "Assurez-vous que l'environnement virtuel est créé"
    exit 1
}

Write-Success "Python trouvé : $pythonPath"

# Vérifier que main.py existe
$mainPath = Join-Path $NovaPath "main.py"
if (-not (Test-Path $mainPath)) {
    Write-Error "main.py introuvable : $mainPath"
    exit 1
}

Write-Success "main.py trouvé"

# Vérifier si NSSM est installé
$nssmPath = "C:\nssm\win64\nssm.exe"
if (-not (Test-Path $nssmPath)) {
    Write-Warning "NSSM non trouvé : $nssmPath"
    Write-Info "Téléchargement de NSSM..."

    # Télécharger NSSM
    $nssmUrl = "https://nssm.cc/ci/nssm-2.24-101-g897c7ad.zip"
    $nssmZip = "$env:TEMP\nssm.zip"
    $nssmExtract = "$env:TEMP\nssm"

    try {
        Invoke-WebRequest -Uri $nssmUrl -OutFile $nssmZip
        Expand-Archive -Path $nssmZip -DestinationPath $nssmExtract -Force

        # Copier NSSM dans C:\nssm
        $nssmExe = Get-ChildItem -Path $nssmExtract -Recurse -Filter "nssm.exe" | Select-Object -First 1
        $nssmDest = "C:\nssm\win64"
        New-Item -ItemType Directory -Force -Path $nssmDest | Out-Null
        Copy-Item $nssmExe.FullName -Destination $nssmDest -Force

        # Ajouter au PATH
        $currentPath = [Environment]::GetEnvironmentVariable("Path", [EnvironmentVariableTarget]::Machine)
        if ($currentPath -notlike "*C:\nssm\win64*") {
            [Environment]::SetEnvironmentVariable("Path", $currentPath + ";C:\nssm\win64", [EnvironmentVariableTarget]::Machine)
        }

        Write-Success "NSSM installé : $nssmDest\nssm.exe"
        $nssmPath = "$nssmDest\nssm.exe"

    } catch {
        Write-Error "Impossible de télécharger NSSM : $_"
        Write-Info "Téléchargez manuellement depuis : https://nssm.cc/download"
        exit 1
    }
}

Write-Success "NSSM trouvé : $nssmPath"

# Vérifier si le service existe déjà
$serviceExists = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($serviceExists) {
    Write-Warning "Le service $ServiceName existe déjà"
    $response = Read-Host "Voulez-vous le supprimer et le recréer ? (y/N)"
    if ($response -eq 'y' -or $response -eq 'Y') {
        Write-Info "Arrêt du service..."
        & $nssmPath stop $ServiceName

        Write-Info "Suppression du service..."
        & $nssmPath remove $ServiceName confirm

        Write-Success "Service supprimé"
    } else {
        Write-Info "Configuration annulée"
        exit 0
    }
}

# Créer le dossier logs
$logsPath = Join-Path $NovaPath "logs"
if (-not (Test-Path $logsPath)) {
    New-Item -ItemType Directory -Force -Path $logsPath | Out-Null
    Write-Success "Dossier logs créé : $logsPath"
}

# Installer le service
Write-Info "Installation du service $ServiceName..."
& $nssmPath install $ServiceName $pythonPath $mainPath

if ($LASTEXITCODE -ne 0) {
    Write-Error "Erreur lors de l'installation du service"
    exit 1
}

Write-Success "Service installé"

# Configurer le service
Write-Info "Configuration du service..."

# Working directory
& $nssmPath set $ServiceName AppDirectory $NovaPath

# Logs
$stdoutLog = Join-Path $logsPath "service.log"
$stderrLog = Join-Path $logsPath "service-error.log"
& $nssmPath set $ServiceName AppStdout $stdoutLog
& $nssmPath set $ServiceName AppStderr $stderrLog

# Rotation des logs (10 MB max)
& $nssmPath set $ServiceName AppStdoutCreationDisposition 4
& $nssmPath set $ServiceName AppStderrCreationDisposition 4
& $nssmPath set $ServiceName AppRotateFiles 1
& $nssmPath set $ServiceName AppRotateOnline 1
& $nssmPath set $ServiceName AppRotateSeconds 86400
& $nssmPath set $ServiceName AppRotateBytes 10485760

# Démarrage automatique
& $nssmPath set $ServiceName Start SERVICE_AUTO_START

# Redémarrage en cas d'échec
& $nssmPath set $ServiceName AppThrottle 5000
& $nssmPath set $ServiceName AppExit Default Restart
& $nssmPath set $ServiceName AppRestartDelay 5000

Write-Success "Service configuré"

# Configurer le pare-feu
Write-Info "Configuration du pare-feu..."

# Supprimer règle existante si présente
$existingRule = Get-NetFirewallRule -DisplayName "NOVA Backend" -ErrorAction SilentlyContinue
if ($existingRule) {
    Remove-NetFirewallRule -DisplayName "NOVA Backend"
}

# Créer nouvelle règle
New-NetFirewallRule -DisplayName "NOVA Backend" `
    -Direction Inbound `
    -LocalPort 8000 `
    -Protocol TCP `
    -Action Allow `
    -Profile Any `
    -Description "Autoriser le trafic vers NOVA Backend (port 8000)"

Write-Success "Règle de pare-feu créée"

# Démarrer le service
Write-Info "Démarrage du service..."
& $nssmPath start $ServiceName

Start-Sleep -Seconds 3

# Vérifier le statut
$status = & $nssmPath status $ServiceName
if ($status -like "*SERVICE_RUNNING*") {
    Write-Success "Service démarré avec succès"
} else {
    Write-Error "Le service n'a pas pu démarrer"
    Write-Info "Vérifiez les logs : $stderrLog"
    exit 1
}

# Tester le backend
Write-Info "Test du backend..."
Start-Sleep -Seconds 2

try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing
    Write-Success "Backend accessible : $($response.StatusCode)"
} catch {
    Write-Warning "Backend non accessible : $_"
    Write-Info "Le service peut prendre quelques secondes à démarrer"
    Write-Info "Vérifiez les logs : $stdoutLog"
}

# Résumé
Write-Host ""
Write-Host "=========================================="
Write-Host "  Installation terminée"
Write-Host "=========================================="
Write-Host ""
Write-Host "Service Windows : $ServiceName"
Write-Host "Statut : $(& $nssmPath status $ServiceName)"
Write-Host ""
Write-Host "Logs :"
Write-Host "  - Stdout : $stdoutLog"
Write-Host "  - Stderr : $stderrLog"
Write-Host ""
Write-Host "Commandes utiles :"
Write-Host "  - Démarrer   : nssm start $ServiceName"
Write-Host "  - Arrêter    : nssm stop $ServiceName"
Write-Host "  - Redémarrer : nssm restart $ServiceName"
Write-Host "  - Statut     : nssm status $ServiceName"
Write-Host "  - Logs       : Get-Content '$stdoutLog' -Tail 50 -Wait"
Write-Host ""
Write-Host "Backend accessible sur : http://localhost:8000"
Write-Host ""

Write-Success "Configuration réussie !"
