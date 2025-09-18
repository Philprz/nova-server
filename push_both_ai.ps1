# Script pour push sur les deux repositories NOVA POC avec analyse IA avancée
# Repository principal: https://github.com/Philprz/nova-server
# Repository secondaire: https://github.com/www-it-spirit-com/NOVAPOC
# Usage: .\push_both_ai.ps1 ["Message de commit"] [-UseAI] [-AIProvider "OpenAI|Claude|Local"] [-Force] [-WithTags] [-AllTags]
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
    [string]$APIKey = "",

    [Parameter(Mandatory=$false)]
    [switch]$Force,          # Utilise --force-with-lease

    [Parameter(Mandatory=$false)]
    [switch]$WithTags,       # Pousse aussi les tags liés ( --follow-tags )

    [Parameter(Mandatory=$false)]
    [switch]$AllTags         # Pousse toutes les tags ( --tags )
)

# Ajouter Git au PATH si nécessaire
$gitPath = "C:\Program Files\Git\bin"
if ((Test-Path $gitPath) -and ($env:PATH -notlike "*$gitPath*")) {
    $env:PATH = "$gitPath;$env:PATH"
}

Write-Host "=== PUSH DUAL REPOSITORY NOVA POC - VERSION IA AVANCÉE ===" -ForegroundColor "Cyan"
Write-Host ""

# Fonction pour gérer les erreurs Git
function ThrowIfFailed($message) {
    if ($LASTEXITCODE -ne 0) { throw $message }
}

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

                $currentFunction = ""
                $currentClass = ""
                $hunkContext = @()
                $addedLines = @()
                $removedLines = @()

                foreach ($line in $diffContent) {
                    if ($line -match '^@@.*@@\s*(.*)$') {
                        $hunkContext = $matches[1]
                        if ($hunkContext -match '(def|function|func|method)\s+(\w+)') { $currentFunction = $matches[2] }
                        elseif ($hunkContext -match '(class|interface|struct)\s+(\w+)') { $currentClass = $matches[2] }
                    }
                    elseif ($line -match '^\+[^+]') {
                        $addedLine = $line.Substring(1)
                        $addedLines += $addedLine
                        $fileAnalysis.Changes += @{
                            'Type' = 'Added'
                            'Line' = $addedLine
                            'Context' = if ($currentFunction) { "in function $currentFunction" } elseif ($currentClass) { "in class $currentClass" } else { "at file level" }
                            'Purpose' = Get-LinePurpose $addedLine $file
                        }
                    }
                    elseif ($line -match '^-[^-]') {
                        $removedLine = $line.Substring(1)
                        $removedLines += $removedLine
                        $fileAnalysis.Changes += @{
                            'Type' = 'Removed'
                            'Line' = $removedLine
                            'Context' = if ($currentFunction) { "in function $currentFunction" } elseif ($currentClass) { "in class $currentClass" } else { "at file level" }
                            'Purpose' = Get-LinePurpose $removedLine $file
                        }
                    }
                }

                $fileAnalysis.Context = Get-ChangeIntent -Added $addedLines -Removed $removedLines -File $file
                $detailedAnalysis.Changes += $fileAnalysis
            }
        }
    }

    $detailedAnalysis.Impact = Get-GlobalImpact -Changes $detailedAnalysis.Changes
    $detailedAnalysis.Rationale = New-ChangeRationale -Analysis $detailedAnalysis
    return $detailedAnalysis
}

# Fonction pour analyser le but d'une ligne de code
function Get-LinePurpose {
    param($line, $file)
    $purpose = ""
    if ($line -match '(import|from|require|include|using)\s+(.+)') { $purpose = "Import de dépendance: $($matches[2])" }
    elseif ($line -match '(def|function|func|method|async def)\s+(\w+)\s*\((.*?)\)') {
        $funcName = $matches[2]; $params = $matches[3]; $purpose = "Définition de fonction '$funcName' avec paramètres: $params"
    }
    elseif ($line -match '(fetch|axios|requests\.(get|post|put|delete)|HttpClient)') { $purpose = "Appel API/HTTP" }
    elseif ($line -match '(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)\s+') { $purpose = "Opération base de données" }
    elseif ($line -match '(try|catch|except|finally|throw|raise)') { $purpose = "Gestion d'erreurs" }
    elseif ($line -match '(validate|check|verify|assert|require)') { $purpose = "Validation/vérification" }
    elseif ($line -match '(log|logger|console\.(log|error|warn)|print)') { $purpose = "Logging/débogage" }
    elseif ($line -match '(config|setting|option|parameter|env)') { $purpose = "Configuration" }
    elseif ($line -match '(auth|token|password|encrypt|decrypt|hash|security)') { $purpose = "Sécurité/authentification" }
    else {
        switch -Regex ([System.IO.Path]::GetExtension($file)) {
            '\.(py|js|ts)$' {
                if ($line -match '^\s*(#|//)\s*(.+)') { $purpose = "Commentaire: $($matches[2])" }
                elseif ($line -match '(return|yield)') { $purpose = "Retour de valeur" }
            }
            '\.sql$' { $purpose = "Requête SQL" }
            '\.(json|yaml|yml)$' { $purpose = "Donnée de configuration" }
        }
    }
    return $purpose
}

# Fonction pour analyser l'intention des changements
function Get-ChangeIntent {
    param($Added, $Removed, $File)
    $intent = @{ 'Type'=''; 'Description'=''; 'Confidence'=0 }
    $addedText = $Added -join ' '; $removedText = $Removed -join ' '

    if ($Added.Count -gt $Removed.Count * 2) {
        $intent.Type='Feature'; $intent.Description="Ajout de nouvelle fonctionnalité"; $intent.Confidence=80
        if ($addedText -match 'class\s+\w+') { $intent.Description="Création d'une nouvelle classe"; $intent.Confidence=95 }
        elseif ($addedText -match '(def|function)\s+\w+') { $intent.Description="Ajout de nouvelle(s) fonction(s)"; $intent.Confidence=90 }
        elseif ($addedText -match '(route|endpoint|api)') { $intent.Description="Ajout d'un nouvel endpoint API"; $intent.Confidence=95 }
    }
    elseif ($removedText -match '(bug|error|fix|issue)' -or $addedText -match '(fix|patch|correct|resolve)') {
        $intent.Type='Fix'; $intent.Description="Correction de bug"; $intent.Confidence=85
        if ($addedText -match 'try.*catch|except') { $intent.Description="Ajout de gestion d'erreurs"; $intent.Confidence=95 }
        elseif ($addedText -match '(null|undefined|None)') { $intent.Description="Correction de valeurs null/undefined"; $intent.Confidence=90 }
    }
    elseif ($Added.Count -gt 0 -and $Removed.Count -gt 0 -and [Math]::Abs($Added.Count - $Removed.Count) -lt 5) {
        $intent.Type='Refactor'; $intent.Description="Refactoring du code"; $intent.Confidence=75
        if ($addedText -match 'async|await' -and $removedText -notmatch 'async|await') { $intent.Description="Migration vers code asynchrone"; $intent.Confidence=95 }
    }
    elseif ($addedText -match '(cache|optimize|performance|fast|quick)') { $intent.Type='Performance'; $intent.Description="Optimisation des performances"; $intent.Confidence=80 }
    elseif ($addedText -match '(security|auth|encrypt|sanitize|escape|validate)') { $intent.Type='Security'; $intent.Description="Amélioration de la sécurité"; $intent.Confidence=90 }
    return $intent
}

# Fonction pour analyser l'impact global
function Get-GlobalImpact {
    param($Changes)
    $impacts = @()
    $filesByType = $Changes | Group-Object { [System.IO.Path]::GetExtension($_.File) }
    foreach ($group in $filesByType) {
        $impact = @{ 'Area'=''; 'Severity'=''; 'Description'='' }
        switch -Regex ($group.Name) {
            '\.(py|js|ts|java|cs)$' { $impact.Area='Backend/Logic'; $impact.Severity='High'; $impact.Description="Modifications de la logique métier" }
            '\.(jsx|tsx|vue|html|css)$' { $impact.Area='Frontend/UI'; $impact.Severity='Medium'; $impact.Description="Modifications de l''interface utilisateur" }
            '\.(sql|migration)$' { $impact.Area='Database'; $impact.Severity='Critical'; $impact.Description="Modifications du schéma de base de données" }
            '\.(json|yaml|yml|ini|conf)$' { $impact.Area='Configuration'; $impact.Severity='Medium'; $impact.Description="Modifications de configuration" }
        }
        if ($impact.Area) { $impacts += $impact }
    }
    return $impacts
}

# Fonction pour générer le raisonnement des changements (corrige le mapping impact/extension)
function New-ChangeRationale {
    param($Analysis)
    $rationale = @()

    foreach ($change in $Analysis.Changes) {
        if ($change.Context) {
            $reason = @{ 'File'=$change.File; 'Why'=""; 'What'=""; 'Impact'="" }

            switch ($change.Context.Type) {
                'Feature'    { $reason.Why = "Pour ajouter une nouvelle capacité au système" }
                'Fix'        { $reason.Why = "Pour résoudre un problème existant" }
                'Refactor'   { $reason.Why = "Pour améliorer la qualité et la maintenabilité du code" }
                'Performance'{ $reason.Why = "Pour optimiser les performances du système" }
                'Security'   { $reason.Why = "Pour renforcer la sécurité de l'application" }
            }

            $reason.What = $change.Context.Description

            # Recalcule l'impact à partir de l'extension du fichier
            $ext = [System.IO.Path]::GetExtension($change.File)
            $impact = switch -Regex ($ext) {
                '\.(py|js|ts|java|cs)$'      { @{Area='Backend/Logic';      Description="Modifications de la logique métier"} ; break }
                '\.(jsx|tsx|vue|html|css)$'  { @{Area='Frontend/UI';        Description="Modifications de l''interface utilisateur"} ; break }
                '\.(sql|migration)$'         { @{Area='Database';           Description="Modifications du schéma de base de données"} ; break }
                '\.(json|yaml|yml|ini|conf)$'{ @{Area='Configuration';      Description="Modifications de configuration"} ; break }
                default                      { $null }
            }
            if ($impact) { $reason.Impact = $impact.Description }

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
            $currentAPIKey = if ($APIKey) { $APIKey } else { $env:OPENAI_API_KEY }
            if (-not $currentAPIKey) { Write-Host "Clé API OpenAI non fournie. Utilisez -APIKey ou définissez OPENAI_API_KEY." -ForegroundColor Red; return $null }
            $model = if ($env:OPENAI_MODEL) { $env:OPENAI_MODEL } else { "gpt-4" }
            $headers = @{ "Authorization" = "Bearer $currentAPIKey"; "Content-Type" = "application/json" }
            $body = @{
                "model" = $model
                "messages" = @(
                    @{ "role" = "system"; "content" = "Tu es un expert en développement logiciel qui génère des messages de commit Git précis et détaillés." },
                    @{ "role" = "user"; "content" = $prompt }
                )
                "temperature" = 0.3
                "max_tokens" = 1000
            } | ConvertTo-Json -Depth 10

            try { $response = Invoke-RestMethod -Uri "https://api.openai.com/v1/chat/completions" -Method Post -Headers $headers -Body $body; return $response.choices[0].message.content }
            catch { Write-Host "Erreur lors de l'appel à OpenAI: $_" -ForegroundColor Red; return $null }
        }
        "Claude" {
            $currentAPIKey = if ($APIKey) { $APIKey } else { $env:ANTHROPIC_API_KEY }
            if (-not $currentAPIKey) { Write-Host "Clé API Anthropic non fournie. Utilisez -APIKey ou définissez ANTHROPIC_API_KEY." -ForegroundColor Red; return $null }
            $model = if ($env:ANTHROPIC_MODEL) { $env:ANTHROPIC_MODEL } else { "claude-3-opus-20240229" }
            $headers = @{ "x-api-key" = $currentAPIKey; "anthropic-version" = "2023-06-01"; "content-type" = "application/json" }
            $body = @{
                "model" = $model
                "max_tokens" = 1000
                "messages" = @(@{ "role" = "user"; "content" = $prompt })
                "temperature" = 0.3
            } | ConvertTo-Json -Depth 10

            try { $response = Invoke-RestMethod -Uri "https://api.anthropic.com/v1/messages" -Method Post -Headers $headers -Body $body; return $response.content[0].text }
            catch { Write-Host "Erreur lors de l'appel à Claude: $_" -ForegroundColor Red; return $null }
        }
    }
    return $null
}

# Fonction pour générer un message de commit intelligent et détaillé
function New-DetailedCommitMessage {
    param($Analysis, $UseAI = $false, $AIProvider = "Local", $APIKey = "")

    if ($UseAI -and $APIKey) {
        $aiMessage = Invoke-AIAnalysis -Changes $Analysis -Provider $AIProvider -APIKey $APIKey
        if ($aiMessage) { return $aiMessage } else { Write-Host "Échec de l'analyse IA, utilisation de l'analyse locale" -ForegroundColor Yellow }
    }

    if (-not $Analysis -or -not $Analysis.Changes -or $Analysis.Changes.Count -eq 0) {
        return "chore(repo): commit sans changements détectés`nAucun changement détecté par l'analyse."
    }

    $primaryChange = $Analysis.Changes[0]
    $changeType = if ($primaryChange.Context.Type) { $primaryChange.Context.Type.ToLower() } else { "update" }

    $commitType = switch ($changeType) {
        "feature"      { "feat" }
        "fix"          { "fix" }
        "refactor"     { "refactor" }
        "performance"  { "perf" }
        "security"     { "security" }
        Default        { "chore" }
    }

    $scope = ""
    if ($Analysis.Impact.Count -gt 0 -and $null -ne $Analysis.Impact[0].Area) {
        $scope = $Analysis.Impact[0].Area.ToLower() -replace '/', '-'
    } elseif ($Analysis.Impact.Count -gt 0) {
        $scope = "default-scope"
    }

    $title = "$commitType$(if ($scope) { "($scope)" }): $($primaryChange.Context.Description)"

    $body = @()
    $body += "`nCHANGEMENTS EFFECTUÉS:"
    foreach ($change in $Analysis.Changes) {
        $body += "`n📁 $($change.File):"
        $grouped = $change.Changes | Group-Object { $_.Type }
        foreach ($group in $grouped) {
            $body += "  $($group.Name):"
            foreach ($item in $group.Group | Select-Object -First 5) {
                if ($item.Purpose) { $body += "    - $($item.Purpose) $($item.Context)" }
                else { $body += "    - $($item.Line.Trim()) $($item.Context)" }
            }
            if ($group.Count -gt 5) { $body += "    ... et $($group.Count - 5) autres modifications" }
        }
    }

    if ($Analysis.Rationale.Count -gt 0) {
        $body += "`nRAISONS DES MODIFICATIONS:"
        foreach ($reason in $Analysis.Rationale) {
            $body += "- $($reason.Why)$(if ($reason.What) { "  → $($reason.What)" })"
        }
    }

    if ($Analysis.Impact.Count -gt 0) {
        $body += "`nIMPACT:"
        foreach ($impact in $Analysis.Impact) { $body += "- [$($impact.Severity)] $($impact.Area): $($impact.Description)" }
    }

    $body += "`nDÉTAILS TECHNIQUES:"
    $totalAdditions = 0; $totalDeletions = 0; $functionsModified = @(); $classesModified = @()

    foreach ($change in $Analysis.Changes) {
        $additions = ($change.Changes | Where-Object { $_.Type -eq 'Added' }).Count
        $deletions = ($change.Changes | Where-Object { $_.Type -eq 'Removed' }).Count
        $totalAdditions += $additions; $totalDeletions += $deletions
        foreach ($c in $change.Changes) {
            if ($c.Context -match 'function (\w+)') { $functionsModified += $matches[1] }
            elseif ($c.Context -match 'class (\w+)') { $classesModified += $matches[1] }
        }
    }

    $body += "- Lignes ajoutées: +$totalAdditions"
    $body += "- Lignes supprimées: -$totalDeletions"
    if ($functionsModified.Count -gt 0) { $body += "- Fonctions modifiées: $((($functionsModified | Select-Object -Unique)) -join ', ')" }
    if ($classesModified.Count -gt 0)   { $body += "- Classes modifiées: $((($classesModified | Select-Object -Unique)) -join ', ')" }

    $finalMessage = "$title`n$($body -join "`n")"
    return $finalMessage
}

# ================== DÉBUT DU SCRIPT PRINCIPAL ==================

# 1) Sécurité : vérifier que le repo est propre avant de commencer
Write-Host "🔍 Vérification de l'état du repository..." -ForegroundColor "Yellow"
$statusOutput = git status --porcelain
ThrowIfFailed "❌ git status a échoué."
if ($statusOutput -and $statusOutput.Trim() -ne "") {
    Write-Host "Changements détectés, analyse en cours..." -ForegroundColor "Yellow"

    if ([string]::IsNullOrEmpty($CommitMessage)) {
        $changedFiles = git diff --name-only HEAD
        if (-not $changedFiles) { $changedFiles = git diff --name-only --cached }
        Write-Host "`nAnalyse approfondie des changements..." -ForegroundColor "Cyan"

        $deepAnalysis = Get-DeepCodeAnalysis -files $changedFiles

        Write-Host "`n📊 RÉSUMÉ DE L'ANALYSE:" -ForegroundColor "Magenta"
        Write-Host "Fichiers modifiés: $($deepAnalysis.Changes.Count)" -ForegroundColor "White"
        foreach ($change in $deepAnalysis.Changes) { Write-Host "  - $($change.File): $($change.Context.Description)" -ForegroundColor "Gray" }

        if ($deepAnalysis.Impact.Count -gt 0) {
            Write-Host "`n🎯 IMPACT:" -ForegroundColor "Yellow"
            foreach ($impact in $deepAnalysis.Impact) {
                $color = switch ($impact.Severity) { "Critical" { "Red" } "High" { "Yellow" } "Medium" { "Cyan" } Default { "Gray" } }
                Write-Host "  [$($impact.Severity)] $($impact.Area): $($impact.Description)" -ForegroundColor $color
            }
        }

        Write-Host "`n🤖 Génération du message de commit..." -ForegroundColor "Cyan"
        if ($UseAI -and [string]::IsNullOrEmpty($APIKey)) {
            Write-Host "ATTENTION: -UseAI spécifié mais aucune clé API fournie" -ForegroundColor "Yellow"
            Write-Host "Utilisez -APIKey 'votre-clé' ou définissez la variable d'environnement:" -ForegroundColor "Yellow"
            Write-Host "  Pour OpenAI: `$env:OPENAI_API_KEY" -ForegroundColor "Gray"
            Write-Host "  Pour Claude: `$env:ANTHROPIC_API_KEY" -ForegroundColor "Gray"
            if ($AIProvider -eq "OpenAI" -and $env:OPENAI_API_KEY) { $APIKey = $env:OPENAI_API_KEY; Write-Host "Clé API OpenAI trouvée dans l'environnement" -ForegroundColor "Green" }
            elseif ($AIProvider -eq "Claude" -and $env:ANTHROPIC_API_KEY) { $APIKey = $env:ANTHROPIC_API_KEY; Write-Host "Clé API Claude trouvée dans l'environnement" -ForegroundColor "Green" }
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
        } else {
            Write-Host "Entrez votre message de commit: " -NoNewline -ForegroundColor "Cyan"
            $CommitMessage = Read-Host
        }
    }

    Write-Host "`n📦 Ajout des fichiers et commit..." -ForegroundColor "Cyan"
    git add .
    ThrowIfFailed "Échec de l'ajout des fichiers."
    git commit -m "$CommitMessage"
    ThrowIfFailed "Échec du commit."
    Write-Host "✅ Commit effectué avec succès" -ForegroundColor "Green"
} else {
    Write-Host "ℹ️  Aucun changement à commiter" -ForegroundColor "Gray"
}

# 2) Déterminer la branche courante
$branch = (git rev-parse --abbrev-ref HEAD).Trim()
ThrowIfFailed "Impossible de déterminer la branche courante."
Write-Host "🚀 Branche courante : $branch" -ForegroundColor "Cyan"

# 3) Préparer les options de push
$forceOpt    = $null; if ($Force)    { $forceOpt    = "--force-with-lease" }
$followTags  = $null; if ($WithTags) { $followTags  = "--follow-tags" }
$allTags     = $null; if ($AllTags)  { $allTags     = "--tags" }

Write-Host ""

# 4) Push vers repository principal (origin)
Write-Host "⬆️  Push vers repository principal (origin/$branch)..." -ForegroundColor "Green"
try {
    git push origin $branch $forceOpt $followTags
    ThrowIfFailed "Échec du push vers origin."
    if ($AllTags) {
        Write-Host "🏷️  Pousse toutes les tags vers origin..." -ForegroundColor "Yellow"
        git push origin --tags
        ThrowIfFailed "Échec du push des tags vers origin."
    }
    Write-Host "✅ Push réussi vers repository principal" -ForegroundColor "Green"
}
catch {
    $pushResult = git push origin $branch $forceOpt $followTags 2>&1
    if ($pushResult -match "fetch first|Updates were rejected") {
        Write-Host "⚠️  Changements distants détectés, synchronisation en cours..." -ForegroundColor "Yellow"
        Write-Host "📥 Récupération des changements distants..." -ForegroundColor "Yellow"
        try {
            git pull origin $branch
            ThrowIfFailed "Échec de la synchronisation."
            Write-Host "🔄 Synchronisation réussie, nouveau push..." -ForegroundColor "Yellow"
            git push origin $branch $forceOpt $followTags
            ThrowIfFailed "Échec du push après synchronisation."
            if ($AllTags) {
                Write-Host "🏷️  Pousse toutes les tags vers origin..." -ForegroundColor "Yellow"
                git push origin --tags
                ThrowIfFailed "Échec du push des tags vers origin."
            }
            Write-Host "✅ Push réussi vers repository principal après synchronisation" -ForegroundColor "Green"
        }
        catch {
            Write-Host "❌ Erreur lors de la synchronisation: $_" -ForegroundColor "Red"
            exit 1
        }
    } else {
        Write-Host "❌ Erreur lors du push vers repository principal: $_" -ForegroundColor "Red"
        exit 1
    }
}

# 5) Push vers repository secondaire
Write-Host "⬆️  Push vers repository secondaire (secondary/$branch)..." -ForegroundColor "Blue"

$remotes = git remote
if ($remotes -notcontains "secondary") {
    git remote add secondary https://github.com/www-it-spirit-com/NOVAPOC.git
    ThrowIfFailed "Impossible d'ajouter le remote secondary."
    Write-Host "🔗 Remote secondaire ajouté" -ForegroundColor "Yellow"
}

Write-Host "🔍 Vérification de l'existence du repository secondaire..." -ForegroundColor "Yellow"
try {
    git ls-remote https://github.com/www-it-spirit-com/NOVAPOC.git | Out-Null
    ThrowIfFailed "Repository secondaire inaccessible."
    try {
        git push secondary $branch $forceOpt $followTags
        ThrowIfFailed "Échec du push vers secondary."
        if ($AllTags) {
            Write-Host "🏷️  Pousse toutes les tags vers secondary..." -ForegroundColor "Yellow"
            git push secondary --tags
            ThrowIfFailed "Échec du push des tags vers secondary."
        }
        Write-Host "✅ Push réussi vers repository secondaire" -ForegroundColor "Blue"
    }
    catch {
        Write-Host "❌ Erreur lors du push vers repository secondaire: $_" -ForegroundColor "Red"
        Write-Host "⚠️  Le push vers le repository principal a réussi, mais pas vers le secondaire" -ForegroundColor "Yellow"
    }
}
catch {
    Write-Host "❌ ATTENTION: Le repository secondaire 'NOVAPOC' n'existe pas ou n'est pas accessible" -ForegroundColor "Red"
    Write-Host "⚠️  Veuillez vérifier l'accès au repository ou corriger l'URL" -ForegroundColor "Yellow"
    Write-Host "✅ Le push vers le repository principal a réussi" -ForegroundColor "Green"
}

Write-Host ""
Write-Host "🎉 === PUSH TERMINÉ ===" -ForegroundColor "Cyan"

if (-not (Test-Path ".ai_commit_initialized")) {
    Write-Host "`n💡 CONSEILS D'UTILISATION:" -ForegroundColor "Yellow"
    Write-Host "- Message personnalisé: .\push_both_ai.ps1 'Mon message de commit'" -ForegroundColor "Gray"
    Write-Host "- Avec IA OpenAI: .\push_both_ai.ps1 -UseAI -AIProvider OpenAI" -ForegroundColor "Gray"
    Write-Host "- Avec IA Claude: .\push_both_ai.ps1 -UseAI -AIProvider Claude" -ForegroundColor "Gray"
    Write-Host "- Push forcé: .\push_both_ai.ps1 -Force" -ForegroundColor "Gray"
    Write-Host "- Avec tags: .\push_both_ai.ps1 -WithTags" -ForegroundColor "Gray"
    Write-Host "- Toutes les tags: .\push_both_ai.ps1 -AllTags" -ForegroundColor "Gray"
    Write-Host "- Définissez vos clés API dans l'environnement pour éviter de les taper:" -ForegroundColor "Gray"
    Write-Host "  `$env:OPENAI_API_KEY = 'votre-clé-openai'" -ForegroundColor "DarkGray"
    Write-Host "  `$env:ANTHROPIC_API_KEY = 'votre-clé-claude'" -ForegroundColor "DarkGray"
    "" | Out-File -FilePath ".ai_commit_initialized" -Force
}
