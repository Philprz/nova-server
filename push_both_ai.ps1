# Script pour push sur les deux repositories NOVA POC avec analyse IA avancée
# Repository principal: https://github.com/Philprz/nova-server
# Repository secondaire: https://github.com/www-it-spirit-com/NOVAPOC
# Usage: .\push_both_ai.ps1 ["Message de commit"] [-UseAI] [-AIProvider "OpenAI|Claude|Local"]
# Si aucun message n'est fourni, le script génèrera un message intelligent

param(
    [Parameter(Mandatory=$false)]
    [string]$CommitMessage = "",
    
    [Parameter(Mandatory=$false)]
    [switch]$UseAI,
    
    [Parameter(Mandatory=$false)]
    [ValidateSet("OpenAI", "Claude", "Local")]
    [string]$AIProvider = "Local",
    
    [Parameter(Mandatory=$false)]
    [string]$APIKey = ""
)

Write-Host "=== PUSH DUAL REPOSITORY NOVA POC - VERSION IA AVANCÉE ===" -ForegroundColor "Cyan"
Write-Host ""

# Fonction pour analyser en profondeur les changements de code
function Get-DeepCodeAnalysis {
    param($files)
    
    $detailedAnalysis = @{
        'Changes' = @()
        'Context' = @{}
        'Impact' = @()
        'Rationale' = @()
    }
    
    foreach ($file in $files) {
        if (Test-Path $file) {
            # Obtenir le diff unifié avec contexte étendu
            $diffContent = git diff HEAD -U10 -- $file
            
            if ($diffContent) {
                $fileAnalysis = @{
                    'File' = $file
                    'Extension' = [System.IO.Path]::GetExtension($file)
                    'Changes' = @()
                    'Functions' = @()
                    'Classes' = @()
                    'Imports' = @()
                    'Context' = ""
                }
                
                # Analyser le contenu ligne par ligne
                $inHunk = $false
                $currentFunction = ""
                $currentClass = ""
                $hunkContext = @()
                $addedLines = @()
                $removedLines = @()
                
                foreach ($line in $diffContent) {
                    # Détecter le contexte de la modification (fonction, classe, etc.)
                    if ($line -match '^@@.*@@\s*(.*)$') {
                        $hunkContext = $matches[1]
                        $inHunk = $true
                        
                        # Extraire le nom de la fonction/méthode du contexte
                        if ($hunkContext -match '(def|function|func|method)\s+(\w+)') {
                            $currentFunction = $matches[2]
                        }
                        elseif ($hunkContext -match '(class|interface|struct)\s+(\w+)') {
                            $currentClass = $matches[2]
                        }
                    }
                    elseif ($line -match '^\+[^+]') {
                        $addedLine = $line.Substring(1)
                        $addedLines += $addedLine
                        
                        # Analyser le contenu de la ligne ajoutée
                        $change = @{
                            'Type' = 'Added'
                            'Line' = $addedLine
                            'Context' = if ($currentFunction) { "in function $currentFunction" } 
                                       elseif ($currentClass) { "in class $currentClass" }
                                       else { "at file level" }
                            'Purpose' = Analyze-LinePurpose $addedLine $file
                        }
                        
                        $fileAnalysis.Changes += $change
                    }
                    elseif ($line -match '^-[^-]') {
                        $removedLine = $line.Substring(1)
                        $removedLines += $removedLine
                        
                        $change = @{
                            'Type' = 'Removed'
                            'Line' = $removedLine
                            'Context' = if ($currentFunction) { "in function $currentFunction" } 
                                       elseif ($currentClass) { "in class $currentClass" }
                                       else { "at file level" }
                            'Purpose' = Analyze-LinePurpose $removedLine $file
                        }
                        
                        $fileAnalysis.Changes += $change
                    }
                }
                
                # Analyser l'intention globale des changements
                $fileAnalysis.Context = Analyze-ChangeIntent -Added $addedLines -Removed $removedLines -File $file
                
                $detailedAnalysis.Changes += $fileAnalysis
            }
        }
    }
    
    # Analyser l'impact global
    $detailedAnalysis.Impact = Analyze-GlobalImpact -Changes $detailedAnalysis.Changes
    
    # Générer le raisonnement
    $detailedAnalysis.Rationale = Generate-ChangeRationale -Analysis $detailedAnalysis
    
    return $detailedAnalysis
}

# Fonction pour analyser le but d'une ligne de code
function Analyze-LinePurpose {
    param($line, $file)
    
    $purpose = ""
    
    # Détection des imports/dépendances
    if ($line -match '(import|from|require|include|using)\s+(.+)') {
        $purpose = "Import de dépendance: $($matches[2])"
    }
    # Détection des définitions de fonction
    elseif ($line -match '(def|function|func|method|async def)\s+(\w+)\s*\((.*?)\)') {
        $funcName = $matches[2]
        $params = $matches[3]
        $purpose = "Définition de fonction '$funcName' avec paramètres: $params"
    }
    # Détection des appels API
    elseif ($line -match '(fetch|axios|requests\.(get|post|put|delete)|HttpClient)') {
        $purpose = "Appel API/HTTP"
    }
    # Détection des requêtes SQL
    elseif ($line -match '(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)\s+') {
        $purpose = "Opération base de données"
    }
    # Détection de la gestion d'erreurs
    elseif ($line -match '(try|catch|except|finally|throw|raise)') {
        $purpose = "Gestion d'erreurs"
    }
    # Détection de validation
    elseif ($line -match '(validate|check|verify|assert|require)') {
        $purpose = "Validation/vérification"
    }
    # Détection de logging
    elseif ($line -match '(log|logger|console\.(log|error|warn)|print)') {
        $purpose = "Logging/débogage"
    }
    # Détection de configuration
    elseif ($line -match '(config|setting|option|parameter|env)') {
        $purpose = "Configuration"
    }
    # Détection de sécurité
    elseif ($line -match '(auth|token|password|encrypt|decrypt|hash|security)') {
        $purpose = "Sécurité/authentification"
    }
    else {
        # Analyse basée sur l'extension du fichier
        switch -Regex ([System.IO.Path]::GetExtension($file)) {
            '\.(py|js|ts)$' {
                if ($line -match '^\s*(#|//)\s*(.+)') {
                    $purpose = "Commentaire: $($matches[2])"
                }
                elseif ($line -match '(return|yield)') {
                    $purpose = "Retour de valeur"
                }
            }
            '\.sql$' {
                $purpose = "Requête SQL"
            }
            '\.(json|yaml|yml)$' {
                $purpose = "Donnée de configuration"
            }
        }
    }
    
    return $purpose
}

# Fonction pour analyser l'intention des changements
function Analyze-ChangeIntent {
    param($Added, $Removed, $File)
    
    $intent = @{
        'Type' = ''
        'Description' = ''
        'Confidence' = 0
    }
    
    # Analyser les patterns de changement
    $addedText = $Added -join ' '
    $removedText = $Removed -join ' '
    
    # Nouvelle fonctionnalité
    if ($Added.Count -gt $Removed.Count * 2) {
        $intent.Type = 'Feature'
        $intent.Description = "Ajout de nouvelle fonctionnalité"
        $intent.Confidence = 80
        
        # Affiner la description
        if ($addedText -match 'class\s+\w+') {
            $intent.Description = "Création d'une nouvelle classe"
            $intent.Confidence = 95
        }
        elseif ($addedText -match '(def|function)\s+\w+') {
            $intent.Description = "Ajout de nouvelle(s) fonction(s)"
            $intent.Confidence = 90
        }
        elseif ($addedText -match '(route|endpoint|api)') {
            $intent.Description = "Ajout d'un nouvel endpoint API"
            $intent.Confidence = 95
        }
    }
    # Correction de bug
    elseif ($removedText -match '(bug|error|fix|issue)' -or $addedText -match '(fix|patch|correct|resolve)') {
        $intent.Type = 'Fix'
        $intent.Description = "Correction de bug"
        $intent.Confidence = 85
        
        if ($addedText -match 'try.*catch|except') {
            $intent.Description = "Ajout de gestion d'erreurs"
            $intent.Confidence = 95
        }
        elseif ($addedText -match '(null|undefined|None)') {
            $intent.Description = "Correction de valeurs null/undefined"
            $intent.Confidence = 90
        }
    }
    # Refactoring
    elseif ($Added.Count -gt 0 -and $Removed.Count -gt 0 -and [Math]::Abs($Added.Count - $Removed.Count) -lt 5) {
        $intent.Type = 'Refactor'
        $intent.Description = "Refactoring du code"
        $intent.Confidence = 75
        
        if ($addedText -match 'async|await' -and $removedText -notmatch 'async|await') {
            $intent.Description = "Migration vers code asynchrone"
            $intent.Confidence = 95
        }
    }
    # Amélioration de performance
    elseif ($addedText -match '(cache|optimize|performance|fast|quick)') {
        $intent.Type = 'Performance'
        $intent.Description = "Optimisation des performances"
        $intent.Confidence = 80
    }
    # Sécurité
    elseif ($addedText -match '(security|auth|encrypt|sanitize|escape|validate)') {
        $intent.Type = 'Security'
        $intent.Description = "Amélioration de la sécurité"
        $intent.Confidence = 90
    }
    
    return $intent
}

# Fonction pour analyser l'impact global
function Analyze-GlobalImpact {
    param($Changes)
    
    $impacts = @()
    
    # Analyser par type de fichier
    $filesByType = $Changes | Group-Object { [System.IO.Path]::GetExtension($_.File) }
    
    foreach ($group in $filesByType) {
        $impact = @{
            'Area' = ''
            'Severity' = ''
            'Description' = ''
        }
        
        switch -Regex ($group.Name) {
            '\.(py|js|ts|java|cs)$' {
                $impact.Area = 'Backend/Logic'
                $impact.Severity = 'High'
                $impact.Description = "Modifications de la logique métier"
            }
            '\.(jsx|tsx|vue|html|css)$' {
                $impact.Area = 'Frontend/UI'
                $impact.Severity = 'Medium'
                $impact.Description = "Modifications de l'interface utilisateur"
            }
            '\.(sql|migration)$' {
                $impact.Area = 'Database'
                $impact.Severity = 'Critical'
                $impact.Description = "Modifications du schéma de base de données"
            }
            '\.(json|yaml|yml|ini|conf)$' {
                $impact.Area = 'Configuration'
                $impact.Severity = 'Medium'
                $impact.Description = "Modifications de configuration"
            }
        }
        
        if ($impact.Area) {
            $impacts += $impact
        }
    }
    
    return $impacts
}

# Fonction pour générer le raisonnement des changements
function Generate-ChangeRationale {
    param($Analysis)
    
    $rationale = @()
    
    foreach ($change in $Analysis.Changes) {
        if ($change.Context) {
            $reason = @{
                'File' = $change.File
                'Why' = ""
                'What' = ""
                'Impact' = ""
            }
            
            # Déterminer le "pourquoi"
            switch ($change.Context.Type) {
                'Feature' {
                    $reason.Why = "Pour ajouter une nouvelle capacité au système"
                }
                'Fix' {
                    $reason.Why = "Pour résoudre un problème existant"
                }
                'Refactor' {
                    $reason.Why = "Pour améliorer la qualité et la maintenabilité du code"
                }
                'Performance' {
                    $reason.Why = "Pour optimiser les performances du système"
                }
                'Security' {
                    $reason.Why = "Pour renforcer la sécurité de l'application"
                }
            }
            
            # Déterminer le "quoi"
            $reason.What = $change.Context.Description
            
            # Déterminer l'impact
            $fileImpact = $Analysis.Impact | Where-Object { $_.Area -match [System.IO.Path]::GetExtension($change.File) }
            if ($fileImpact) {
                $reason.Impact = $fileImpact.Description
            }
            
            $rationale += $reason
        }
    }
    
    return $rationale
}

# Fonction pour appeler une API IA (OpenAI ou Claude)
function Invoke-AIAnalysis {
    param($Changes, $Provider, $APIKey)
    
    $prompt = @"
Analyse les changements suivants dans un repository Git et génère un message de commit détaillé et précis.

CHANGEMENTS:
$($Changes | ConvertTo-Json -Depth 10)

INSTRUCTIONS:
1. Génère un message de commit au format Conventional Commits
2. Le titre doit être concis mais précis (max 72 caractères)
3. Le corps doit expliquer:
   - CE QUI a été changé (liste détaillée)
   - POURQUOI ces changements ont été faits
   - QUEL IMPACT ces changements auront
4. Utilise des bullet points pour la clarté
5. Sois très spécifique sur les fonctions/classes/fichiers modifiés
6. Mentionne les effets de bord potentiels

FORMAT ATTENDU:
<type>(<scope>): <description courte>

<description détaillée>

Changements:
- ...
- ...

Raison:
- ...

Impact:
- ...
"@
    
    switch ($Provider) {
        "OpenAI" {
            $headers = @{
                "Authorization" = "Bearer $APIKey"
                "Content-Type" = "application/json"
            }
            
            $body = @{
                "model" = "gpt-4"
                "messages" = @(
                    @{
                        "role" = "system"
                        "content" = "Tu es un expert en développement logiciel qui génère des messages de commit Git précis et détaillés."
                    },
                    @{
                        "role" = "user"
                        "content" = $prompt
                    }
                )
                "temperature" = 0.3
                "max_tokens" = 1000
            } | ConvertTo-Json -Depth 10
            
            try {
                $response = Invoke-RestMethod -Uri "https://api.openai.com/v1/chat/completions" -Method Post -Headers $headers -Body $body
                return $response.choices[0].message.content
            }
            catch {
                Write-Host "Erreur lors de l'appel à OpenAI: $_" -ForegroundColor Red
                return $null
            }
        }
        
        "Claude" {
            $headers = @{
                "x-api-key" = $APIKey
                "anthropic-version" = "2023-06-01"
                "content-type" = "application/json"
            }
            
            $body = @{
                "model" = "claude-3-opus-20240229"
                "max_tokens" = 1000
                "messages" = @(
                    @{
                        "role" = "user"
                        "content" = $prompt
                    }
                )
                "temperature" = 0.3
            } | ConvertTo-Json -Depth 10
            
            try {
                $response = Invoke-RestMethod -Uri "https://api.anthropic.com/v1/messages" -Method Post -Headers $headers -Body $body
                return $response.content[0].text
            }
            catch {
                Write-Host "Erreur lors de l'appel à Claude: $_" -ForegroundColor Red
                return $null
            }
        }
    }
    
    return $null
}

# Fonction pour générer un message de commit intelligent et détaillé
function New-DetailedCommitMessage {
    param($Analysis, $UseAI = $false, $AIProvider = "Local", $APIKey = "")
    
    if ($UseAI -and $APIKey) {
        $aiMessage = Invoke-AIAnalysis -Changes $Analysis -Provider $AIProvider -APIKey $APIKey
        if ($aiMessage) {
            return $aiMessage
        }
        else {
            Write-Host "Échec de l'analyse IA, utilisation de l'analyse locale" -ForegroundColor Yellow
        }
    }
    
    # Analyse locale détaillée
    $primaryChange = $Analysis.Changes[0]
    $changeType = if ($primaryChange.Context.Type) { $primaryChange.Context.Type.ToLower() } else { "update" }
    
    # Mapper le type de changement au format Conventional Commits
    $commitType = switch ($changeType) {
        "feature" { "feat" }
        "fix" { "fix" }
        "refactor" { "refactor" }
        "performance" { "perf" }
        "security" { "security" }
        default { "chore" }
    }
    
    # Déterminer le scope
    $scope = ""
    if ($Analysis.Impact.Count -gt 0) {
        $scope = $Analysis.Impact[0].Area.ToLower() -replace '/', '-'
    }
    
    # Générer le titre
    $title = "$commitType$(if ($scope) { "($scope)" }): $($primaryChange.Context.Description)"
    
    # Générer le corps détaillé
    $body = @()
    
    # Section: Ce qui a été changé
    $body += "`nCHANGEMENTS EFFECTUÉS:"
    foreach ($change in $Analysis.Changes) {
        $body += "`n📁 $($change.File):"
        
        # Grouper les changements par type
        $grouped = $change.Changes | Group-Object { $_.Type }
        foreach ($group in $grouped) {
            $body += "  $($group.Name):"
            foreach ($item in $group.Group | Select-Object -First 5) {
                if ($item.Purpose) {
                    $body += "    - $($item.Purpose) $($item.Context)"
                }
                else {
                    $body += "    - $($item.Line.Trim()) $($item.Context)"
                }
            }
            if ($group.Count -gt 5) {
                $body += "    ... et $($group.Count - 5) autres modifications"
            }
        }
    }
    
    # Section: Pourquoi ces changements
    if ($Analysis.Rationale.Count -gt 0) {
        $body += "`nRAISONS DES MODIFICATIONS:"
        foreach ($reason in $Analysis.Rationale) {
            $body += "- $($reason.Why)"
            if ($reason.What) {
                $body += "  → $($reason.What)"
            }
        }
    }
    
    # Section: Impact
    if ($Analysis.Impact.Count -gt 0) {
        $body += "`nIMPACT:"
        foreach ($impact in $Analysis.Impact) {
            $body += "- [$($impact.Severity)] $($impact.Area): $($impact.Description)"
        }
    }
    
    # Section: Détails techniques
    $body += "`nDÉTAILS TECHNIQUES:"
    $totalAdditions = 0
    $totalDeletions = 0
    $functionsModified = @()
    $classesModified = @()
    
    foreach ($change in $Analysis.Changes) {
        $additions = ($change.Changes | Where-Object { $_.Type -eq 'Added' }).Count
        $deletions = ($change.Changes | Where-Object { $_.Type -eq 'Removed' }).Count
        $totalAdditions += $additions
        $totalDeletions += $deletions
        
        # Extraire les fonctions et classes modifiées
        foreach ($c in $change.Changes) {
            if ($c.Context -match 'function (\w+)') {
                $functionsModified += $matches[1]
            }
            elseif ($c.Context -match 'class (\w+)') {
                $classesModified += $matches[1]
            }
        }
    }
    
    $body += "- Lignes ajoutées: +$totalAdditions"
    $body += "- Lignes supprimées: -$totalDeletions"
    
    if ($functionsModified.Count -gt 0) {
        $body += "- Fonctions modifiées: $($functionsModified | Select-Object -Unique | Join-String -Separator ', ')"
    }
    
    if ($classesModified.Count -gt 0) {
        $body += "- Classes modifiées: $($classesModified | Select-Object -Unique | Join-String -Separator ', ')"
    }
    
    # Construire le message final
    $finalMessage = "$title`n$($body -join "`n")"
    
    return $finalMessage
}

# ================== DÉBUT DU SCRIPT PRINCIPAL ==================

# Vérifier s'il y a des changements
$status = git status --porcelain
if ($status) {
    Write-Host "Changements détectés, analyse en cours..." -ForegroundColor "Yellow"
    
    # Si aucun message de commit n'est fourni, générer un message intelligent
    if ([string]::IsNullOrEmpty($CommitMessage)) {
        # Récupérer la liste des fichiers modifiés
        $changedFiles = git diff --name-only HEAD
        if (-not $changedFiles) {
            $changedFiles = git diff --name-only --cached
        }
        
        Write-Host "`nAnalyse approfondie des changements..." -ForegroundColor "Cyan"
        
        # Effectuer l'analyse détaillée
        $deepAnalysis = Get-DeepCodeAnalysis -files $changedFiles
        
        # Afficher un résumé de l'analyse
        Write-Host "`n📊 RÉSUMÉ DE L'ANALYSE:" -ForegroundColor "Magenta"
        Write-Host "Fichiers modifiés: $($deepAnalysis.Changes.Count)" -ForegroundColor "White"
        
        foreach ($change in $deepAnalysis.Changes) {
            Write-Host "  - $($change.File): $($change.Context.Description)" -ForegroundColor "Gray"
        }
        
        if ($deepAnalysis.Impact.Count -gt 0) {
            Write-Host "`n🎯 IMPACT:" -ForegroundColor "Yellow"
            foreach ($impact in $deepAnalysis.Impact) {
                $color = switch ($impact.Severity) {
                    "Critical" { "Red" }
                    "High" { "Yellow" }
                    "Medium" { "Cyan" }
                    default { "Gray" }
                }
                Write-Host "  [$($impact.Severity)] $($impact.Area): $($impact.Description)" -ForegroundColor $color
            }
        }
        
        # Générer le message de commit
        Write-Host "`n🤖 Génération du message de commit..." -ForegroundColor "Cyan"
        
        # Vérifier si on doit utiliser une API IA
        if ($UseAI -and [string]::IsNullOrEmpty($APIKey)) {
            Write-Host "ATTENTION: -UseAI spécifié mais aucune clé API fournie" -ForegroundColor "Yellow"
            Write-Host "Utilisez -APIKey 'votre-clé' ou définissez la variable d'environnement:" -ForegroundColor "Yellow"
            Write-Host "  Pour OpenAI: `$env:OPENAI_API_KEY" -ForegroundColor "Gray"
            Write-Host "  Pour Claude: `$env:ANTHROPIC_API_KEY" -ForegroundColor "Gray"
            
            # Essayer de récupérer depuis les variables d'environnement
            if ($AIProvider -eq "OpenAI" -and $env:OPENAI_API_KEY) {
                $APIKey = $env:OPENAI_API_KEY
                Write-Host "Clé API OpenAI trouvée dans l'environnement" -ForegroundColor "Green"
            }
            elseif ($AIProvider -eq "Claude" -and $env:ANTHROPIC_API_KEY) {
                $APIKey = $env:ANTHROPIC_API_KEY
                Write-Host "Clé API Claude trouvée dans l'environnement" -ForegroundColor "Green"
            }
        }
        
        $suggestion = New-DetailedCommitMessage -Analysis $deepAnalysis -UseAI $UseAI -AIProvider $AIProvider -APIKey $APIKey
        
        Write-Host "`n📝 MESSAGE DE COMMIT SUGGÉRÉ:" -ForegroundColor "Green"
        Write-Host "========================================" -ForegroundColor "DarkGray"
        Write-Host $suggestion -ForegroundColor "White"
        Write-Host "========================================" -ForegroundColor "DarkGray"
        
        Write-Host "`nUtiliser ce message? (O/n) " -NoNewline -ForegroundColor "Yellow"
        $response = Read-Host
        
        if ($response -eq "" -or $response -eq "O" -or $response -eq "o") {
            $CommitMessage = $suggestion
        }
        else {
            Write-Host "Entrez votre message de commit: " -NoNewline -ForegroundColor "Cyan"
            $CommitMessage = Read-Host
        }
    }
    
    # Ajouter tous les fichiers et commiter
    git add .
    git commit -m "$CommitMessage"
    Write-Host "Commit effectué avec succès" -ForegroundColor "Green"
    
} else {
    Write-Host "Aucun changement à commiter" -ForegroundColor "Gray"
}

Write-Host ""

# Push vers repository principal (Philprz/nova-server)
Write-Host "Push vers repository principal (Philprz/nova-server)..." -ForegroundColor "Green"
$pushResult = git push origin main 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "Push réussi vers repository principal" -ForegroundColor "Green"
} else {
    Write-Host "Erreur lors du push vers repository principal:" -ForegroundColor "Red"
    Write-Host "$pushResult" -ForegroundColor "Red"
    exit 1
}

Write-Host "Push vers repository secondaire (www-it-spirit-com/NOVAPOC)..." -ForegroundColor "Blue"

# Ajouter le remote secondaire s'il n'existe pas
$remotes = git remote
if ($remotes -notcontains "secondary") {
    git remote add secondary https://github.com/www-it-spirit-com/NOVAPOC.git
    Write-Host "Remote secondaire ajouté" -ForegroundColor "Yellow"
}

# Vérifier d'abord si le repository existe
Write-Host "Vérification de l'existence du repository secondaire..." -ForegroundColor "Yellow"
$repoCheck = git ls-remote https://github.com/www-it-spirit-com/NOVAPOC.git 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ATTENTION: Le repository secondaire 'NOVAPOC' n'existe pas ou n'est pas accessible" -ForegroundColor "Red"
    Write-Host "Erreur: $repoCheck" -ForegroundColor "Red"
    Write-Host "Veuillez vérifier l'accès au repository ou corriger l'URL" -ForegroundColor "Yellow"
    Write-Host "Le push vers le repository principal a réussi" -ForegroundColor "Green"
} else {
    # Le repository existe, procéder au push
    $pushSecondaryResult = git push secondary main 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Push réussi vers repository secondaire" -ForegroundColor "Blue"
    } else {
        Write-Host "Erreur lors du push vers repository secondaire:" -ForegroundColor "Red"
        Write-Host "$pushSecondaryResult" -ForegroundColor "Red"
        Write-Host "Le push vers le repository principal a réussi, mais pas vers le secondaire" -ForegroundColor "Yellow"
    }
}

Write-Host ""
Write-Host "=== PUSH TERMINÉ ===" -ForegroundColor "Cyan"

# Afficher les conseils d'utilisation si c'est la première fois
if (-not (Test-Path ".ai_commit_initialized")) {
    Write-Host "`n💡 CONSEILS D'UTILISATION:" -ForegroundColor "Yellow"
    Write-Host "- Pour utiliser l'IA OpenAI: .\push_both_ai.ps1 -UseAI -AIProvider OpenAI" -ForegroundColor "Gray"
    Write-Host "- Pour utiliser l'IA Claude: .\push_both_ai.ps1 -UseAI -AIProvider Claude" -ForegroundColor "Gray"
    Write-Host "- Définissez vos clés API dans l'environnement pour éviter de les taper" -ForegroundColor "Gray"
    Write-Host "  `$env:OPENAI_API_KEY = 'votre-clé-openai'" -ForegroundColor "DarkGray"
    Write-Host "  `$env:ANTHROPIC_API_KEY = 'votre-clé-claude'" -ForegroundColor "DarkGray"
    
    # Créer le fichier marqueur
    "" | Out-File -FilePath ".ai_commit_initialized" -Force
}