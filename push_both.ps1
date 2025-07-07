# Script pour push sur les deux repositories NOVA POC
# Usage: .\push_both.ps1 ["Message de commit"]
# Si aucun message n'est fourni, le script demandera interactivement

param(
    [Parameter(Mandatory=$false)]
    [string]$CommitMessage = ""
)

Write-Host "=== PUSH DUAL REPOSITORY NOVA POC ===" -ForegroundColor "Cyan"
Write-Host ""

# Vérifier s'il y a des changements
$status = git status --porcelain
if ($status) {
    Write-Host "Changements détectés, ajout et commit..." -ForegroundColor "Yellow"
    
    # Si aucun message de commit n'est fourni, demander interactivement
    if ([string]::IsNullOrEmpty($CommitMessage)) {
        # Récupérer les informations détaillées sur les changements
        $changedFiles = git diff --name-status
        
        # Analyser les changements par type
        $added = @()
        $modified = @()
        $deleted = @()
        
        foreach ($line in $changedFiles) {
            if ($line -match "^A\s+(.+)") { $added += $matches[1] }
            elseif ($line -match "^M\s+(.+)") { $modified += $matches[1] }
            elseif ($line -match "^D\s+(.+)") { $deleted += $matches[1] }
        }
        
        # Analyser l'incidence des changements
        $impacts = @()
        $allChangedFiles = $added + $modified + $deleted
        
        # NOUVELLE FONCTIONNALITÉ : Analyse intelligente du contenu des modifications
        function Get-CodeChanges {
            param($files)
            
            $analysisResults = @{
                'BugFixes' = @()
                'NewFeatures' = @()
                'Refactoring' = @()
                'Configuration' = @()
                'UI_UX' = @()
                'Tests' = @()
            }
            
            foreach ($file in $files) {
                if (Test-Path $file) {
                    # Obtenir le diff détaillé pour ce fichier
                    $diffContent = git diff HEAD -- $file
                    
                    if ($diffContent) {
                        # Analyser les lignes ajoutées (+) et supprimées (-)
                        $addedLines = $diffContent | Where-Object { $_ -match '^\+[^+]' } | ForEach-Object { $_.Substring(1) }
                        $removedLines = $diffContent | Where-Object { $_ -match '^-[^-]' } | ForEach-Object { $_.Substring(1) }
                        
                        # Détection de bug fixes
                        $bugFixPatterns = @(
                            'fix|bug|error|issue|problem|crash|exception|null|undefined',
                            'try.*catch|exception|error.*handling',
                            'validate|validation|check.*null|if.*null',
                            'security|vulnerability|xss|sql.*injection|csrf'
                        )
                        
                        foreach ($pattern in $bugFixPatterns) {
                            if (($addedLines -join ' ') -match $pattern -or ($removedLines -join ' ') -match $pattern) {
                                $analysisResults.BugFixes += @{
                                    'File' = [System.IO.Path]::GetFileName($file)
                                    'Type' = if ($pattern -match 'security') { 'Security Fix' } 
                                            elseif ($pattern -match 'try.*catch') { 'Error Handling' }
                                            elseif ($pattern -match 'validate') { 'Validation Fix' }
                                            else { 'Bug Fix' }
                                    'Details' = ($addedLines | Select-Object -First 2) -join '; '
                                }
                                break
                            }
                        }
                        
                        # Détection de nouvelles fonctionnalités
                        $featurePatterns = @(
                            'def |function |class |interface |async |await',
                            'new.*|add.*|create.*|implement.*',
                            'import.*|from.*import|require\(',
                            'route|endpoint|api|service'
                        )
                        
                        foreach ($pattern in $featurePatterns) {
                            if (($addedLines -join ' ') -match $pattern) {
                                $analysisResults.NewFeatures += @{
                                    'File' = [System.IO.Path]::GetFileName($file)
                                    'Type' = if ($pattern -match 'route|endpoint|api') { 'New API Endpoint' }
                                            elseif ($pattern -match 'class |interface') { 'New Class/Interface' }
                                            elseif ($pattern -match 'def |function') { 'New Function' }
                                            elseif ($pattern -match 'import') { 'New Dependency' }
                                            else { 'New Feature' }
                                    'Details' = ($addedLines | Where-Object { $_ -match $pattern } | Select-Object -First 1)
                                }
                                break
                            }
                        }
                        
                        # Détection de refactoring
                        if ($addedLines.Count -gt 0 -and $removedLines.Count -gt 0) {
                            $refactoringPatterns = @(
                                'rename|refactor|optimize|improve|clean',
                                'move.*|extract.*|split.*'
                            )
                            
                            foreach ($pattern in $refactoringPatterns) {
                                if (($addedLines -join ' ') -match $pattern -or ($removedLines -join ' ') -match $pattern) {
                                    $analysisResults.Refactoring += @{
                                        'File' = [System.IO.Path]::GetFileName($file)
                                        'Type' = 'Code Refactoring'
                                        'Details' = "Refactored code structure"
                                    }
                                    break
                                }
                            }
                        }
                        
                        # Détection de modifications de configuration
                        if ($file -match '\.(json|yaml|yml|xml|ini|conf|config|env)$') {
                            $analysisResults.Configuration += @{
                                'File' = [System.IO.Path]::GetFileName($file)
                                'Type' = 'Configuration Update'
                                'Details' = if ($addedLines.Count -gt $removedLines.Count) { 'Added configuration' } 
                                           elseif ($removedLines.Count -gt $addedLines.Count) { 'Removed configuration' }
                                           else { 'Updated configuration' }
                            }
                        }
                        
                        # Détection de modifications UI/UX
                        if ($file -match '\.(css|scss|html|js|jsx|ts|tsx)$') {
                            $uiPatterns = @('style|css|color|font|layout|responsive|ui|ux|design')
                            foreach ($pattern in $uiPatterns) {
                                if (($addedLines -join ' ') -match $pattern) {
                                    $analysisResults.UI_UX += @{
                                        'File' = [System.IO.Path]::GetFileName($file)
                                        'Type' = 'UI/UX Update'
                                        'Details' = 'Interface improvements'
                                    }
                                    break
                                }
                            }
                        }
                        
                        # Détection de modifications de tests
                        if ($file -match '(test|spec)' -or ($addedLines -join ' ') -match 'test|assert|expect|should') {
                            $analysisResults.Tests += @{
                                'File' = [System.IO.Path]::GetFileName($file)
                                'Type' = if ($addedLines.Count -gt $removedLines.Count) { 'Added Tests' } else { 'Updated Tests' }
                                'Details' = 'Test coverage changes'
                            }
                        }
                    }
                }
            }
            
            return $analysisResults
        }

        # Générer un message de commit intelligent basé sur l'analyse
        function New-SmartCommitMessage {
            param($analysis, $summary)
            
            $commitParts = @()
            $commitType = "feat" # Par défaut
            $scope = ""
            
            # Déterminer le scope basé sur les fichiers modifiés
            $scopePatterns = @{
                'api|routes|endpoints' = 'api'
                'db|database|models|migration' = 'db'
                'ui|frontend|templates|static' = 'ui'
                'auth|login|security' = 'auth'
                'config|settings|env' = 'config'
                'test|spec' = 'test'
                'doc|readme|guide' = 'docs'
                'workflow|scripts' = 'ci'
            }
            
            foreach ($pattern in $scopePatterns.Keys) {
                if ($allChangedFiles -match $pattern) {
                    $scope = $scopePatterns[$pattern]
                    break
                }
            }
            
            # Prioriser les types de modifications
            if ($analysis.BugFixes.Count -gt 0) {
                $commitType = "fix"
                $mainFix = $analysis.BugFixes[0]
                $commitParts += "fix $($mainFix.Type.ToLower()) in $($mainFix.File)"
            }
            elseif ($analysis.NewFeatures.Count -gt 0) {
                $commitType = "feat"
                $mainFeature = $analysis.NewFeatures[0]
                $commitParts += "add $($mainFeature.Type.ToLower()) in $($mainFeature.File)"
            }
            elseif ($analysis.Refactoring.Count -gt 0) {
                $commitType = "refactor"
                $commitParts += "refactor code structure in $($analysis.Refactoring.Count) file(s)"
            }
            elseif ($analysis.Configuration.Count -gt 0) {
                $commitType = "config"
                $configChange = $analysis.Configuration[0]
                $commitParts += "$($configChange.Details.ToLower()) in $($configChange.File)"
            }
            elseif ($analysis.UI_UX.Count -gt 0) {
                $commitType = "style"
                $commitParts += "improve UI/UX in $($analysis.UI_UX.Count) file(s)"
            }
            elseif ($analysis.Tests.Count -gt 0) {
                $commitType = "test"
                $testChange = $analysis.Tests[0]
                $commitParts += "$($testChange.Type.ToLower())"
            }
            
            # Construire le message final
            $mainMessage = if ($commitParts.Count -gt 0) { 
                ($commitParts -join " ").Trim()
            } else { 
                ($summary[0] -replace "^[+*-] ", "").ToLower()
            }
            
            # Appliquer le format Conventional Commits
            $finalMessage = if ($scope) {
                "$commitType($scope): $mainMessage"
            } else {
                "$commitType`: $mainMessage"
            }
            
            return $finalMessage
        }
        
        # Exécuter l'analyse intelligente
        Write-Host "Analyse intelligente des modifications en cours..." -ForegroundColor "Cyan"
        $codeAnalysis = Get-CodeChanges -files $allChangedFiles
        
        # Afficher un résumé de l'analyse dans la console
        Write-Host ""
        Write-Host "=== RÉSULTATS DE L'ANALYSE INTELLIGENTE ===" -ForegroundColor "Yellow"
        
        $totalAnalyzedItems = $codeAnalysis.BugFixes.Count + $codeAnalysis.NewFeatures.Count + $codeAnalysis.Refactoring.Count + $codeAnalysis.Configuration.Count + $codeAnalysis.UI_UX.Count + $codeAnalysis.Tests.Count
        
        if ($totalAnalyzedItems -gt 0) {
            if ($codeAnalysis.BugFixes.Count -gt 0) {
                Write-Host "Bug Fixes détectés: $($codeAnalysis.BugFixes.Count)" -ForegroundColor "Red"
                foreach ($fix in $codeAnalysis.BugFixes | Select-Object -First 2) {
                    Write-Host "   - $($fix.Type) dans $($fix.File)" -ForegroundColor "DarkRed"
                }
            }
            
            if ($codeAnalysis.NewFeatures.Count -gt 0) {
                Write-Host "Nouvelles fonctionnalités: $($codeAnalysis.NewFeatures.Count)" -ForegroundColor "Green"
                foreach ($feature in $codeAnalysis.NewFeatures | Select-Object -First 2) {
                    Write-Host "   - $($feature.Type) dans $($feature.File)" -ForegroundColor "DarkGreen"
                }
            }
            
            if ($codeAnalysis.Refactoring.Count -gt 0) {
                Write-Host "Refactoring détecté: $($codeAnalysis.Refactoring.Count) fichier(s)" -ForegroundColor "Blue"
            }
            
            if ($codeAnalysis.Configuration.Count -gt 0) {
                Write-Host "Modifications config: $($codeAnalysis.Configuration.Count) fichier(s)" -ForegroundColor "Magenta"
            }
            
            if ($codeAnalysis.UI_UX.Count -gt 0) {
                Write-Host "Améliorations UI/UX: $($codeAnalysis.UI_UX.Count) fichier(s)" -ForegroundColor "Cyan"
            }
            
            if ($codeAnalysis.Tests.Count -gt 0) {
                Write-Host "Modifications tests: $($codeAnalysis.Tests.Count) fichier(s)" -ForegroundColor "Yellow"
            }
        } else {
            Write-Host "Aucune modification spécifique détectée - Changements généraux" -ForegroundColor "Gray"
        }
        
        Write-Host "================================================" -ForegroundColor "Yellow"
        Write-Host ""
        
        # Catégoriser les impacts
        $frontendFiles = $allChangedFiles | Where-Object { $_ -match '\.(js|jsx|ts|tsx|css|scss|html)$' }
        $backendFiles = $allChangedFiles | Where-Object { $_ -match '\.(py|java|cs|go|rb|php)$' }
        $configFiles = $allChangedFiles | Where-Object { $_ -match '\.(json|yaml|yml|xml|ini|conf|config|env)$' }
        $docFiles = $allChangedFiles | Where-Object { $_ -match '\.(md|txt|doc|docx|pdf)$' }
        $testFiles = $allChangedFiles | Where-Object { $_ -match '(test|spec|\.test\.|\.spec\.)' }
        $packageFiles = $allChangedFiles | Where-Object { $_ -match '(package\.json|requirements\.txt|pom\.xml|Gemfile|composer\.json|go\.mod)$' }
        $dbFiles = $allChangedFiles | Where-Object { $_ -match '\.(sql|migration)' }
        
        # Analyser les fichiers critiques
        $criticalChanges = @()
        if ($allChangedFiles | Where-Object { $_ -match '(\.env|secrets|credentials|password)' }) {
            $criticalChanges += "Fichiers sensibles modifiés (secrets/credentials)"
        }
        if ($packageFiles.Count -gt 0) {
            $criticalChanges += "Dépendances modifiées - npm/pip install requis"
        }
        if ($dbFiles.Count -gt 0) {
            $criticalChanges += "Modifications base de données - migration requise"
        }
        
        # Construire l'analyse d'impact
        if ($frontendFiles.Count -gt 0) {
            $impacts += "Frontend: $($frontendFiles.Count) fichier(s) - Impact UI/UX"
        }
        if ($backendFiles.Count -gt 0) {
            $impacts += "Backend: $($backendFiles.Count) fichier(s) - Impact API/Logique"
        }
        if ($configFiles.Count -gt 0) {
            $impacts += "Configuration: $($configFiles.Count) fichier(s) - Redémarrage possible"
        }
        if ($testFiles.Count -gt 0) {
            $impacts += "Tests: $($testFiles.Count) fichier(s) - Couverture modifiée"
        }
        if ($docFiles.Count -gt 0) {
            $impacts += "Documentation: $($docFiles.Count) fichier(s)"
        }
        
        # Ajouter les résultats de l'analyse intelligente aux impacts
        if ($codeAnalysis.BugFixes.Count -gt 0) {
            $impacts += "Bug Fixes: $($codeAnalysis.BugFixes.Count) correction(s) identifiée(s)"
        }
        if ($codeAnalysis.NewFeatures.Count -gt 0) {
            $impacts += "New Features: $($codeAnalysis.NewFeatures.Count) nouvelle(s) fonctionnalité(s)"
        }
        if ($codeAnalysis.Refactoring.Count -gt 0) {
            $impacts += "Refactoring: $($codeAnalysis.Refactoring.Count) amélioration(s) de code"
        }

        # Construire un résumé détaillé
        $summary = @()
        if ($added.Count -gt 0) {
            $summary += "Ajouté: " + ($added | Select-Object -First 3 | ForEach-Object { [System.IO.Path]::GetFileName($_) }) -join ", "
            if ($added.Count -gt 3) { $summary[-1] += " (+$($added.Count - 3) autres)" }
        }
        if ($modified.Count -gt 0) {
            $summary += "Modifié: " + ($modified | Select-Object -First 3 | ForEach-Object { [System.IO.Path]::GetFileName($_) }) -join ", "
            if ($modified.Count -gt 3) { $summary[-1] += " (+$($modified.Count - 3) autres)" }
        }
        if ($deleted.Count -gt 0) {
            $summary += "Supprimé: " + ($deleted | Select-Object -First 3 | ForEach-Object { [System.IO.Path]::GetFileName($_) }) -join ", "
            if ($deleted.Count -gt 3) { $summary[-1] += " (+$($deleted.Count - 3) autres)" }
        }
        
        # Obtenir les statistiques globales
        $totalChanges = git diff --shortstat
        if ($totalChanges -match "(\d+) files? changed(?:, (\d+) insertions?\(\+\))?(?:, (\d+) deletions?\(-\))?") {
            $filesChanged = $matches[1]
            $insertions = if ($matches[2]) { $matches[2] } else { "0" }
            $deletions = if ($matches[3]) { $matches[3] } else { "0" }
            $summary += "Total: $filesChanged fichier(s), +$insertions/-$deletions lignes"
        }
        
        # Créer la suggestion de message INTELLIGENTE
        $suggestion = New-SmartCommitMessage -analysis $codeAnalysis -summary $summary
        
        # Créer un rapport détaillé de l'analyse intelligente
        $intelligentAnalysisReport = @()
        if ($codeAnalysis.BugFixes.Count -gt 0) {
            $intelligentAnalysisReport += "CORRECTIONS DE BUGS DÉTECTÉES:"
            foreach ($fix in $codeAnalysis.BugFixes) {
                $intelligentAnalysisReport += "   • $($fix.Type) dans $($fix.File)"
                if ($fix.Details) { $intelligentAnalysisReport += "     - $($fix.Details)" }
            }
            $intelligentAnalysisReport += ""
        }
        
        if ($codeAnalysis.NewFeatures.Count -gt 0) {
            $intelligentAnalysisReport += "NOUVELLES FONCTIONNALITÉS DÉTECTÉES:"
            foreach ($feature in $codeAnalysis.NewFeatures) {
                $intelligentAnalysisReport += "   • $($feature.Type) dans $($feature.File)"
                if ($feature.Details) { $intelligentAnalysisReport += "     - $($feature.Details)" }
            }
            $intelligentAnalysisReport += ""
        }
        
        if ($codeAnalysis.Refactoring.Count -gt 0) {
            $intelligentAnalysisReport += "REFACTORING DÉTECTÉ:"
            foreach ($refactor in $codeAnalysis.Refactoring) {
                $intelligentAnalysisReport += "   • $($refactor.Type) dans $($refactor.File)"
            }
            $intelligentAnalysisReport += ""
        }
        
        if ($codeAnalysis.Configuration.Count -gt 0) {
            $intelligentAnalysisReport += "MODIFICATIONS DE CONFIGURATION:"
            foreach ($config in $codeAnalysis.Configuration) {
                $intelligentAnalysisReport += "   • $($config.Details) dans $($config.File)"
            }
            $intelligentAnalysisReport += ""
        }
        
        if ($codeAnalysis.UI_UX.Count -gt 0) {
            $intelligentAnalysisReport += "AMÉLIORATIONS UI/UX:"
            foreach ($ui in $codeAnalysis.UI_UX) {
                $intelligentAnalysisReport += "   • $($ui.Type) dans $($ui.File)"
            }
            $intelligentAnalysisReport += ""
        }
        
        if ($codeAnalysis.Tests.Count -gt 0) {
            $intelligentAnalysisReport += "MODIFICATIONS DE TESTS:"
            foreach ($test in $codeAnalysis.Tests) {
                $intelligentAnalysisReport += "   • $($test.Type) dans $($test.File)"
            }
            $intelligentAnalysisReport += ""
        }
        
        if ($intelligentAnalysisReport.Count -eq 0) {
            $intelligentAnalysisReport += "Aucune modification spécifique détectée par l'analyse intelligente"
            $intelligentAnalysisReport += "Les changements semblent être des modifications générales"
        }
        
        # Demander confirmation avec le message suggéré
        Write-Host "Message de commit suggéré par l'IA:" -ForegroundColor "Green"
        Write-Host "$suggestion" -ForegroundColor "Yellow"
        Write-Host ""
        
        $response = Read-Host "Utiliser ce message? (O/n)"
        if ($response -eq "" -or $response -eq "O" -or $response -eq "o") {
            $CommitMessage = $suggestion
        } else {
            $CommitMessage = Read-Host "Entrez votre message de commit"
        }
    }
    
    # Ajouter tous les fichiers
    git add .
    
    # Commiter avec le message fourni
    git commit -m $CommitMessage
    
    Write-Host "Commit créé: $CommitMessage" -ForegroundColor "Green"
} else {
    Write-Host "Aucun changement à commiter" -ForegroundColor "Gray"
}

Write-Host ""

# Push vers repository principal (entreprise)
Write-Host "Push vers repository principal (www-it-spirit-com)..." -ForegroundColor "Green"
$pushResult = git push origin main 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "Push réussi vers repository principal" -ForegroundColor "Green"
} else {
    Write-Host "Erreur lors du push vers repository principal:" -ForegroundColor "Red"
    Write-Host "$pushResult" -ForegroundColor "Red"
    exit 1
}

Write-Host "Push vers repository secondaire (NOVAPOC)..." -ForegroundColor "Blue"

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
    Write-Host "ATTENTION: Le repository secondaire 'nova-poc-commercial' n'existe pas sur GitHub" -ForegroundColor "Red"
    Write-Host "Erreur: $repoCheck" -ForegroundColor "Red"
    Write-Host "Veuillez créer le repository sur GitHub ou corriger l'URL" -ForegroundColor "Yellow"
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