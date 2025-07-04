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
        $diffStats = git diff --stat --stat-width=80
        
        # Analyser les changements par type
        $added = @()
        $modified = @()
        $deleted = @()
        
        foreach ($line in $changedFiles) {
            if ($line -match "^A\s+(.+)") { $added += $matches[1] }
            elseif ($line -match "^M\s+(.+)") { $modified += $matches[1] }
            elseif ($line -match "^D\s+(.+)") { $deleted += $matches[1] }
        }
        
        # NOUVELLE FONCTIONNALITÉ : Analyse intelligente du contenu des modifications
        function Analyze-CodeChanges {
            param($files)

            $analysisResults = @{
                'BugFixes' = @()
                'NewFeatures' = @()
                'Refactoring' = @()
                'Configuration' = @()
                'Documentation' = @()
                'Tests' = @()
                'Dependencies' = @()
                'Security' = @()
                'Performance' = @()
                'UI_UX' = @()
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
                                'move.*|extract.*|split.*',
                                'const |let |var |final '
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

        # Exécuter l'analyse intelligente
        Write-Host "🔍 Analyse intelligente des modifications en cours..." -ForegroundColor "Cyan"
        $codeAnalysis = Analyze-CodeChanges -files $allChangedFiles

        # Générer un message de commit intelligent basé sur l'analyse
        function Generate-SmartCommitMessage {
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

            # Prioriser les types de modifications avec plus de précision
            if ($analysis.BugFixes.Count -gt 0) {
                $commitType = "fix"
                $mainFix = $analysis.BugFixes[0]

                # Analyser le type de bug fix plus précisément
                $bugDescription = switch ($mainFix.Type) {
                    'Security Fix' { "security vulnerability" }
                    'Error Handling' { "error handling" }
                    'Validation Fix' { "input validation" }
                    default { "bug" }
                }

                $commitParts += $bugDescription
                if ($mainFix.File) {
                    $commitParts += "in $($mainFix.File -replace '\.(py|js|ts|jsx|tsx|css|html)$', '')"
                }

                if ($analysis.BugFixes.Count -gt 1) {
                    $commitParts += "and $($analysis.BugFixes.Count - 1) other fixes"
                }
            }
            elseif ($analysis.NewFeatures.Count -gt 0) {
                $commitType = "feat"
                $mainFeature = $analysis.NewFeatures[0]

                # Analyser le type de feature plus précisément
                $featureDescription = switch ($mainFeature.Type) {
                    'New API Endpoint' { "API endpoint" }
                    'New Class/Interface' { "class/interface" }
                    'New Function' { "function" }
                    'New Dependency' { "dependency integration" }
                    default { "feature" }
                }

                $commitParts += $featureDescription
                if ($mainFeature.File) {
                    $commitParts += "in $($mainFeature.File -replace '\.(py|js|ts|jsx|tsx|css|html)$', '')"
                }

                if ($analysis.NewFeatures.Count -gt 1) {
                    $commitParts += "and $($analysis.NewFeatures.Count - 1) other features"
                }
            }
            elseif ($analysis.Refactoring.Count -gt 0) {
                $commitType = "refactor"
                $commitParts += "code structure"
                if ($analysis.Refactoring.Count -eq 1) {
                    $commitParts += "in $($analysis.Refactoring[0].File -replace '\.(py|js|ts|jsx|tsx|css|html)$', '')"
                } else {
                    $commitParts += "in $($analysis.Refactoring.Count) files"
                }
            }
            elseif ($analysis.Configuration.Count -gt 0) {
                $commitType = "config"
                $configChange = $analysis.Configuration[0]
                $commitParts += $configChange.Details.ToLower()
                if ($configChange.File) {
                    $commitParts += "in $($configChange.File -replace '\.(json|yaml|yml|xml|ini|conf|config|env)$', '')"
                }
            }
            elseif ($analysis.UI_UX.Count -gt 0) {
                $commitType = "style"
                $commitParts += "UI/UX improvements"
                if ($analysis.UI_UX.Count -eq 1) {
                    $commitParts += "in $($analysis.UI_UX[0].File -replace '\.(css|scss|html|js|jsx|ts|tsx)$', '')"
                } else {
                    $commitParts += "across $($analysis.UI_UX.Count) components"
                }
            }
            elseif ($analysis.Tests.Count -gt 0) {
                $commitType = "test"
                $testChange = $analysis.Tests[0]
                $commitParts += $testChange.Type.ToLower()
                if ($testChange.File) {
                    $commitParts += "for $($testChange.File -replace '(test|spec)', '' -replace '\.(py|js|ts|jsx|tsx)$', '')"
                }
            }

            # Construire le message final avec format conventionnel
            $mainMessage = if ($commitParts.Count -gt 0) {
                ($commitParts -join " ").Trim()
            } else {
                ($summary[0] -replace "^[➕📝🗑️] ", "").ToLower()
            }

            # Appliquer le format Conventional Commits
            $finalMessage = if ($scope) {
                "$commitType($scope): $mainMessage"
            } else {
                "$commitType``: $mainMessage
            }

            # Capitaliser la première lettre du message
            $finalMessage = $finalMessage.Substring(0,1).ToUpper() + $finalMessage.Substring(1)
"
            return $finalMessage
        }

        # Exécuter l'analyse intelligente
        Write-Host "🔍 Analyse intelligente des modifications en cours..." -ForegroundColor "Cyan"
        $codeAnalysis = Analyze-CodeChanges -files $allChangedFiles

        # Capitaliser la première lettre du message
        $finalMessage = $finalMessage.Substring(0,1).ToUpper() + $finalMessage.Substring(1)

            return $finalMessage
    }

    # Exécuter l'analyse intelligente
    Write-Host "🔍 Analyse intelligente des modifications en cours..." -ForegroundColor "Cyan"
    $codeAnalysis = Analyze-CodeChanges -files $allChangedFiles

        # Afficher un résumé de l'analyse dans la console
        Write-Host ""
        Write-Host "🤖 === RÉSULTATS DE L'ANALYSE INTELLIGENTE ===" -ForegroundColor "Yellow"

        $totalAnalyzedItems = $codeAnalysis.BugFixes.Count + $codeAnalysis.NewFeatures.Count + $codeAnalysis.Refactoring.Count + $codeAnalysis.Configuration.Count + $codeAnalysis.UI_UX.Count + $codeAnalysis.Tests.Count

        if ($totalAnalyzedItems -gt 0) {
            if ($codeAnalysis.BugFixes.Count -gt 0) {
                Write-Host "🐛 Bug Fixes détectés: $($codeAnalysis.BugFixes.Count)" -ForegroundColor "Red"
                    foreach ($fix in $codeAnalysis.BugFixes | Select-Object -First 2) {
                        Write-Host "   └─ $($fix.Type) dans $($fix.File)" -ForegroundColor "DarkRed"
                    }
                }

                if ($codeAnalysis.NewFeatures.Count -gt 0) {
                    Write-Host "✨ Nouvelles fonctionnalités: $($codeAnalysis.NewFeatures.Count)" -ForegroundColor "Green"
                    foreach ($feature in $codeAnalysis.NewFeatures | Select-Object -First 2) {
                        Write-Host "   └─ $($feature.Type) dans $($feature.File)" -ForegroundColor "DarkGreen"
                    }
                }

                if ($codeAnalysis.Refactoring.Count -gt 0) {
                    Write-Host "♻️ Refactoring détecté: $($codeAnalysis.Refactoring.Count) fichier(s)" -ForegroundColor "Blue"
                }

                if ($codeAnalysis.Configuration.Count -gt 0) {
                    Write-Host "🔧 Modifications config: $($codeAnalysis.Configuration.Count) fichier(s)" -ForegroundColor "Magenta"
                }

                if ($codeAnalysis.UI_UX.Count -gt 0) {
                    Write-Host "🎨 Améliorations UI/UX: $($codeAnalysis.UI_UX.Count) fichier(s)" -ForegroundColor "Cyan"
                }

                if ($codeAnalysis.Tests.Count -gt 0) {
                    Write-Host "🧪 Modifications tests: $($codeAnalysis.Tests.Count) fichier(s)" -ForegroundColor "Yellow"
                }
            } else {
                Write-Host "ℹ️ Aucune modification spécifique détectée - Changements généraux" -ForegroundColor "Gray"
            }

            Write-Host "================================================" -ForegroundColor "Yellow"
            Write-Host ""

            # Capitaliser la première lettre du message
            $finalMessage = $finalMessage.Substring(0,1).ToUpper() + $finalMessage.Substring(1)

            return $finalMessage
        }
        }

        # Catégoriser les impacts (code existant amélioré)
        if ($frontendFiles.Count -gt 0) {
            $impacts += "🎨 Frontend: $($frontendFiles.Count) fichier(s) - Impact UI/UX"
        }
        if ($backendFiles.Count -gt 0) {
            $impacts += "⚙️ Backend: $($backendFiles.Count) fichier(s) - Impact API/Logique"
        }
        if ($configFiles.Count -gt 0) {
            $impacts += "🔧 Configuration: $($configFiles.Count) fichier(s) - Redémarrage possible"
        }
        if ($testFiles.Count -gt 0) {
            $impacts += "🧪 Tests: $($testFiles.Count) fichier(s) - Couverture modifiée"
        }
        if ($docFiles.Count -gt 0) {
            $impacts += "📄 Documentation: $($docFiles.Count) fichier(s)"
        }

        # Ajouter les résultats de l'analyse intelligente aux impacts
        if ($codeAnalysis.BugFixes.Count -gt 0) {
            $impacts += "🐛 Bug Fixes: $($codeAnalysis.BugFixes.Count) correction(s) identifiée(s)"
        }
        if ($codeAnalysis.NewFeatures.Count -gt 0) {
            $impacts += "✨ New Features: $($codeAnalysis.NewFeatures.Count) nouvelle(s) fonctionnalité(s)"
        }
        if ($codeAnalysis.Refactoring.Count -gt 0) {
            $impacts += "♻️ Refactoring: $($codeAnalysis.Refactoring.Count) amélioration(s) de code"
        }
        if ($codeAnalysis.Security.Count -gt 0) {
            $impacts += "🔒 Security: $($codeAnalysis.Security.Count) correction(s) de sécurité"
        }

        # Construire un résumé détaillé
        $summary = @()
        if ($added.Count -gt 0) {
            $summary += "➕ Ajouté: " + ($added | Select-Object -First 3 | ForEach-Object { [System.IO.Path]::GetFileName($_) }) -join ", "
            if ($added.Count -gt 3) { $summary[-1] += " (+$($added.Count - 3) autres)" }
        }
        if ($modified.Count -gt 0) {
            $summary += "📝 Modifié: " + ($modified | Select-Object -First 3 | ForEach-Object { [System.IO.Path]::GetFileName($_) }) -join ", "
            if ($modified.Count -gt 3) { $summary[-1] += " (+$($modified.Count - 3) autres)" }
        }
        if ($deleted.Count -gt 0) {
            $summary += "🗑️ Supprimé: " + ($deleted | Select-Object -First 3 | ForEach-Object { [System.IO.Path]::GetFileName($_) }) -join ", "
            if ($deleted.Count -gt 3) { $summary[-1] += " (+$($deleted.Count - 3) autres)" }
        }

        # Obtenir les statistiques globales
        $totalChanges = git diff --shortstat
        if ($totalChanges -match "(\d+) files? changed(?:, (\d+) insertions?\(\+\))?(?:, (\d+) deletions?\(-\))?") {
            $filesChanged = $matches[1]
            $insertions = if ($matches[2]) { $matches[2] } else { "0" }
            $deletions = if ($matches[3]) { $matches[3] } else { "0" }
            $summary += "📊 Total: $filesChanged fichier(s), +$insertions/-$deletions lignes"
        }

        # Créer la suggestion de message INTELLIGENTE
        $suggestion = Generate-SmartCommitMessage -analysis $codeAnalysis -summary $summary
        
        # Créer un rapport détaillé de l'analyse intelligente
        $intelligentAnalysisReport = @()
        if ($codeAnalysis.BugFixes.Count -gt 0) {
            $intelligentAnalysisReport += "🐛 CORRECTIONS DE BUGS DÉTECTÉES:"
            foreach ($fix in $codeAnalysis.BugFixes) {
                $intelligentAnalysisReport += "   • $($fix.Type) dans $($fix.File)"
                if ($fix.Details) { $intelligentAnalysisReport += "     └─ $($fix.Details)" }
            }
            $intelligentAnalysisReport += ""
        }

        if ($codeAnalysis.NewFeatures.Count -gt 0) {
            $intelligentAnalysisReport += "✨ NOUVELLES FONCTIONNALITÉS DÉTECTÉES:"
            foreach ($feature in $codeAnalysis.NewFeatures) {
                $intelligentAnalysisReport += "   • $($feature.Type) dans $($feature.File)"
                if ($feature.Details) { $intelligentAnalysisReport += "     └─ $($feature.Details)" }
            }
            $intelligentAnalysisReport += ""
        }

        if ($codeAnalysis.Refactoring.Count -gt 0) {
            $intelligentAnalysisReport += "♻️ REFACTORING DÉTECTÉ:"
            foreach ($refactor in $codeAnalysis.Refactoring) {
                $intelligentAnalysisReport += "   • $($refactor.Type) dans $($refactor.File)"
            }
            $intelligentAnalysisReport += ""
        }

        if ($codeAnalysis.Configuration.Count -gt 0) {
            $intelligentAnalysisReport += "🔧 MODIFICATIONS DE CONFIGURATION:"
            foreach ($config in $codeAnalysis.Configuration) {
                $intelligentAnalysisReport += "   • $($config.Details) dans $($config.File)"
            }
            $intelligentAnalysisReport += ""
        }

        if ($codeAnalysis.UI_UX.Count -gt 0) {
            $intelligentAnalysisReport += "🎨 AMÉLIORATIONS UI/UX:"
            foreach ($ui in $codeAnalysis.UI_UX) {
                $intelligentAnalysisReport += "   • $($ui.Type) dans $($ui.File)"
            }
            $intelligentAnalysisReport += ""
        }

        if ($codeAnalysis.Tests.Count -gt 0) {
            $intelligentAnalysisReport += "🧪 MODIFICATIONS DE TESTS:"
            foreach ($test in $codeAnalysis.Tests) {
                $intelligentAnalysisReport += "   • $($test.Type) dans $($test.File)"
            }
            $intelligentAnalysisReport += ""
        }

        if ($intelligentAnalysisReport.Count -eq 0) {
            $intelligentAnalysisReport += "ℹ️ Aucune modification spécifique détectée par l'analyse intelligente"
            $intelligentAnalysisReport += "Les changements semblent être des modifications générales"
        }

        # Créer la fenêtre de dialogue améliorée avec analyse intelligente
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing

        $form = New-Object System.Windows.Forms.Form
        $form.Text = "Message de commit - Analyse Intelligente IA"
        $form.Size = New-Object System.Drawing.Size(900, 750)  # Agrandir pour la nouvelle section
        $form.StartPosition = "CenterScreen"
        $form.Font = New-Object System.Drawing.Font("Consolas", 9)

        # Label principal
        $label = New-Object System.Windows.Forms.Label
        $label.Location = New-Object System.Drawing.Point(10, 10)
        $label.Size = New-Object System.Drawing.Size(860, 20)
        $label.Text = "Message de commit (généré par IA) :"
        $label.Font = New-Object System.Drawing.Font("Consolas", 9, [System.Drawing.FontStyle]::Bold)

        # TextBox pour le message
        $textBox = New-Object System.Windows.Forms.TextBox
        $textBox.Location = New-Object System.Drawing.Point(10, 35)
        $textBox.Size = New-Object System.Drawing.Size(860, 25)
        $textBox.Text = $suggestion
        $textBox.Font = New-Object System.Drawing.Font("Consolas", 10, [System.Drawing.FontStyle]::Bold)
        $textBox.BackColor = [System.Drawing.Color]::LightYellow
        $textBox.Select($suggestion.Length, 0)

        # NOUVELLE SECTION : Analyse Intelligente IA
        $aiAnalysisLabel = New-Object System.Windows.Forms.Label
        $aiAnalysisLabel.Location = New-Object System.Drawing.Point(10, 70)
        $aiAnalysisLabel.Size = New-Object System.Drawing.Size(860, 20)
        $aiAnalysisLabel.Text = "🤖 Analyse Intelligente IA - Détection automatique des modifications :"
        $aiAnalysisLabel.Font = New-Object System.Drawing.Font("Consolas", 9, [System.Drawing.FontStyle]::Bold)
        $aiAnalysisLabel.ForeColor = [System.Drawing.Color]::DarkBlue

        # TextBox pour l'analyse intelligente
        $aiAnalysisBox = New-Object System.Windows.Forms.TextBox
        $aiAnalysisBox.Location = New-Object System.Drawing.Point(10, 95)
        $aiAnalysisBox.Size = New-Object System.Drawing.Size(860, 120)
        $aiAnalysisBox.Multiline = $true
        $aiAnalysisBox.ScrollBars = "Both"
        $aiAnalysisBox.ReadOnly = $true
        $aiAnalysisBox.Text = $intelligentAnalysisReport -join "`r`n"
        $aiAnalysisBox.Font = New-Object System.Drawing.Font("Consolas", 8)
        $aiAnalysisBox.BackColor = [System.Drawing.Color]::AliceBlue

        # Label pour le résumé (repositionné)
        $summaryLabel = New-Object System.Windows.Forms.Label
        $summaryLabel.Location = New-Object System.Drawing.Point(10, 225)
        $summaryLabel.Size = New-Object System.Drawing.Size(860, 20)
        $summaryLabel.Text = "📋 Résumé des changements :"
        $summaryLabel.Font = New-Object System.Drawing.Font("Consolas", 9, [System.Drawing.FontStyle]::Bold)

        # TextBox pour le résumé (repositionnée)
        $summaryBox = New-Object System.Windows.Forms.TextBox
        $summaryBox.Location = New-Object System.Drawing.Point(10, 250)
        $summaryBox.Size = New-Object System.Drawing.Size(860, 80)
        $summaryBox.Multiline = $true
        $summaryBox.ScrollBars = "Both"
        $summaryBox.ReadOnly = $true
        $summaryBox.Text = $summary -join "`r`n"
        $summaryBox.Font = New-Object System.Drawing.Font("Consolas", 8)

        # Label pour l'impact (repositionné)
        $impactLabel = New-Object System.Windows.Forms.Label
        $impactLabel.Location = New-Object System.Drawing.Point(10, 340)
        $impactLabel.Size = New-Object System.Drawing.Size(860, 20)
        $impactLabel.Text = "⚡ Analyse d'impact :"
        $impactLabel.Font = New-Object System.Drawing.Font("Consolas", 9, [System.Drawing.FontStyle]::Bold)

        # TextBox pour l'impact (repositionnée)
        $impactBox = New-Object System.Windows.Forms.TextBox
        $impactBox.Location = New-Object System.Drawing.Point(10, 365)
        $impactBox.Size = New-Object System.Drawing.Size(860, 80)
        $impactBox.Multiline = $true
        $impactBox.ScrollBars = "Both"
        $impactBox.ReadOnly = $true
        $impactText = if ($impacts.Count -gt 0) { $impacts -join "`r`n" } else { "Aucun impact spécifique détecté" }
        if ($criticalChanges.Count -gt 0) {
            $impactText += "`r`n`r`n⚠️ ATTENTION - Changements critiques :`r`n" + ($criticalChanges -join "`r`n")
        }
        
        $impactBox.Text = $impactText
        $impactBox.Font = New-Object System.Drawing.Font("Consolas", 9)
        if ($criticalChanges.Count -gt 0) {
            $impactBox.ForeColor = [System.Drawing.Color]::DarkRed
        }

        # Label pour les détails
        $detailsLabel = New-Object System.Windows.Forms.Label
        $detailsLabel.Location = New-Object System.Drawing.Point(10, 360)
        $detailsLabel.Size = New-Object System.Drawing.Size(760, 20)
        $detailsLabel.Text = "Détails techniques :"
        $detailsLabel.Font = New-Object System.Drawing.Font("Consolas", 9, [System.Drawing.FontStyle]::Bold)

        # TextBox pour les détails des changements
        $detailsBox = New-Object System.Windows.Forms.TextBox
        $detailsBox.Location = New-Object System.Drawing.Point(10, 385)
        $detailsBox.Size = New-Object System.Drawing.Size(760, 120)
        $detailsBox.Multiline = $true
        $detailsBox.ScrollBars = "Both"
        $detailsBox.ReadOnly = $true
        $detailsBox.Text = $diffStats
        $detailsBox.Font = New-Object System.Drawing.Font("Consolas", 8)

        # Boutons
        $okButton = New-Object System.Windows.Forms.Button
        $okButton.Location = New-Object System.Drawing.Point(300, 530)
        $okButton.Size = New-Object System.Drawing.Size(100, 30)
        $okButton.Text = "OK"
        $okButton.DialogResult = [System.Windows.Forms.DialogResult]::OK
        $form.AcceptButton = $okButton

        $cancelButton = New-Object System.Windows.Forms.Button
        $cancelButton.Location = New-Object System.Drawing.Point(420, 530)
        $cancelButton.Size = New-Object System.Drawing.Size(100, 30)
        $cancelButton.Text = "Annuler"
        $cancelButton.DialogResult = [System.Windows.Forms.DialogResult]::Cancel

        # Ajouter tous les contrôles
        $form.Controls.AddRange(@($label, $textBox, $summaryLabel, $summaryBox, $impactLabel, $impactBox, $detailsLabel, $detailsBox, $okButton, $cancelButton))
        $form.Topmost = $true

        $result = $form.ShowDialog()

        if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
            $CommitMessage = $textBox.Text
        } elseif ($result -eq [System.Windows.Forms.DialogResult]::Cancel) {
            Write-Host "❌ Commit annulé par l'utilisateur" -ForegroundColor "Red"
            exit
        } else {
            $CommitMessage = $suggestion
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
try {
    git push origin main
    Write-Host "✅ Push réussi vers repository principal" -ForegroundColor "Green"
} catch {
    Write-Host "❌ Erreur push repository principal: $_" -ForegroundColor "Red"
}

Write-Host ""

# Push vers repository personnel
Write-Host "Push vers repository personnel (Philprz)..." -ForegroundColor "Yellow"
try {
    git push personal main  
    Write-Host "✅ Push réussi vers repository personnel" -ForegroundColor "Green"
} catch {
    Write-Host "❌ Erreur push repository personnel: $_" -ForegroundColor "Red"
}

Write-Host ""
Write-Host "=== PUSH TERMINÉ SUR LES DEUX REPOSITORIES ===" -ForegroundColor "Cyan"

# Afficher le statut final
git status --short