# Script pour push sur les deux repositories NOVA POC avec analyse IA
# Repository principal: https://github.com/Philprz/nova-server
# Repository secondaire: https://github.com/www-it-spirit-com/NOVAPOC

param(
    [string]$CommitMessage = "",
    [switch]$UseAI,
    [ValidateSet("OpenAI", "Claude", "Local")]
    [string]$AIProvider = "Local",
    [string]$APIKey = ""
)

# Configuration Git
$gitPath = "C:\Program Files\Git\bin"
if ((Test-Path $gitPath) -and ($env:PATH -notlike "*$gitPath*")) {
    $env:PATH = "$gitPath;$env:PATH"
}

# Bannière simplifiée
Write-Host "`n=== PUSH DUAL REPOSITORY ===" -ForegroundColor "Cyan"

# Importer toutes les fonctions d'analyse depuis le script original
. $PSScriptRoot\push_both_ai.ps1

# Fonction de logging unifiée pour réduire la verbosité
function Write-CompactLog {
    param(
        [string]$Message,
        [string]$Level = "Info",
        [switch]$NoNewline
    )
    
    $icon = switch ($Level) {
        "Info" { "ℹ️" }
        "Success" { "✅" }
        "Warning" { "⚠️" }
        "Error" { "❌" }
        "Process" { "⚡" }
        default { "•" }
    }
    
    $color = switch ($Level) {
        "Info" { "Gray" }
        "Success" { "Green" }
        "Warning" { "Yellow" }
        "Error" { "Red" }
        "Process" { "Cyan" }
        default { "White" }
    }
    
    if ($NoNewline) {
        Write-Host "$icon $Message" -ForegroundColor $color -NoNewline
    }
    else {
        Write-Host "$icon $Message" -ForegroundColor $color
    }
}

# Vérification des changements
$status = git status --porcelain
if ($status) {
    $changedFiles = git diff --name-only HEAD
    if (-not $changedFiles) {
        $changedFiles = git diff --name-only --cached
    }
    
    # Si pas de message fourni, générer un message intelligent
    if (-not $CommitMessage) {
        Write-CompactLog "Analyse des changements..." -Level "Process"
        
        # Analyse approfondie mais affichage simplifié
        $deepAnalysis = Get-DeepCodeAnalysis -files $changedFiles
        
        # Résumé compact
        Write-CompactLog "Fichiers modifiés: $($deepAnalysis.Changes.Count)" -Level "Info"
        
        # Afficher l'impact principal seulement
        if ($deepAnalysis.Impact.Count -gt 0) {
            $mainImpact = $deepAnalysis.Impact | Sort-Object { 
                switch ($_.Severity) {
                    "Critical" { 1 }
                    "High" { 2 }
                    "Medium" { 3 }
                    "Low" { 4 }
                }
            } | Select-Object -First 1
            
            Write-CompactLog "Impact principal: $($mainImpact.Description)" -Level "Warning"
        }
        
        # Génération du message
        if ($UseAI -and $APIKey) {
            Write-CompactLog "Génération IA du message..." -Level "Process"
        }
        else {
            Write-CompactLog "Génération locale du message..." -Level "Process"
        }
        
        $suggestion = New-DetailedCommitMessage -Analysis $deepAnalysis -UseAI $UseAI -AIProvider $AIProvider -APIKey $APIKey
        
        # Affichage simplifié du message suggéré
        Write-Host "`n📝 MESSAGE SUGGÉRÉ:" -ForegroundColor "Green"
        Write-Host "---" -ForegroundColor "DarkGray"
        
        # Afficher seulement les premières lignes du message
        $lines = $suggestion -split "`n"
        $title = $lines[0]
        Write-Host $title -ForegroundColor "White"
        
        if ($lines.Count -gt 1) {
            Write-Host "(+$($lines.Count - 1) lignes de détails)" -ForegroundColor "Gray"
        }
        Write-Host "---" -ForegroundColor "DarkGray"
        
        Write-Host "`nUtiliser ce message? (O/n) " -NoNewline -ForegroundColor "Yellow"
        $response = Read-Host
        
        if ($response -eq 'n' -or $response -eq 'N') {
            Write-Host "Message personnalisé: " -NoNewline -ForegroundColor "Cyan"
            $CommitMessage = Read-Host
        }
        else {
            $CommitMessage = $suggestion
        }
    }
    
    # Commit avec affichage minimal
    git add -A
    git commit -m $CommitMessage | Out-Null
    Write-CompactLog "Commit effectué" -Level "Success"
}
else {
    Write-CompactLog "Aucun changement à commiter" -Level "Info"
    exit 0
}

# Push vers les repositories avec gestion d'erreur simplifiée
Write-CompactLog "Push principal..." -Level "Process"
$pushResult = git push origin main 2>&1

if ($LASTEXITCODE -ne 0) {
    if ($pushResult -match "rejected") {
        Write-CompactLog "Synchronisation requise..." -Level "Warning"
        git pull origin main --no-edit | Out-Null
        
        if ($LASTEXITCODE -eq 0) {
            git push origin main | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-CompactLog "Push principal réussi (après sync)" -Level "Success"
            }
        }
    }
    else {
        Write-CompactLog "Erreur push principal: $($pushResult | Select-Object -First 1)" -Level "Error"
        exit 1
    }
}
else {
    Write-CompactLog "Push principal réussi" -Level "Success"
}

# Push secondaire
Write-CompactLog "Push secondaire..." -Level "Process"

$remotes = git remote
if ($remotes -notcontains "secondary") {
    git remote add secondary https://github.com/www-it-spirit-com/NOVAPOC.git 2>&1 | Out-Null
}

# Vérification simplifiée du repo secondaire
$repoCheck = git ls-remote https://github.com/www-it-spirit-com/NOVAPOC.git 2>&1
if ($repoCheck -match "fatal|not found|error") {
    Write-CompactLog "Repository secondaire inaccessible" -Level "Warning"
}
else {
    $pushSecondaryResult = git push secondary main 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-CompactLog "Push secondaire réussi" -Level "Success"
    }
    else {
        Write-CompactLog "Erreur push secondaire (ignorée)" -Level "Warning"
    }
}

Write-Host "`n✨ Terminé!" -ForegroundColor "Green"