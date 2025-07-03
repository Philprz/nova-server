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
        
        # Analyser l'incidence des changements
        $impacts = @()
        $allChangedFiles = $added + $modified + $deleted
        
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
            $criticalChanges += "⚠️ Fichiers sensibles modifiés (secrets/credentials)"
        }
        if ($packageFiles.Count -gt 0) {
            $criticalChanges += "📦 Dépendances modifiées - npm/pip install requis"
        }
        if ($dbFiles.Count -gt 0) {
            $criticalChanges += "🗄️ Modifications base de données - migration requise"
        }
        
        # Construire l'analyse d'impact
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
        
        # Analyser les modules/composants affectés
        $components = @()
        foreach ($file in $allChangedFiles) {
            if ($file -match "src[/\\]components[/\\]([^/\\]+)") {
                $components += $matches[1]
            } elseif ($file -match "modules[/\\]([^/\\]+)") {
                $components += $matches[1]
            } elseif ($file -match "features[/\\]([^/\\]+)") {
                $components += $matches[1]
            }
        }
        $uniqueComponents = $components | Select-Object -Unique
        
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
        
        # Créer la suggestion de message
        $suggestion = if ($summary.Count -gt 0) {
            $summary[0] -replace "^[➕📝🗑️] ", ""
        } else {
            "Update POC NOVA"
        }
        
        # Créer la fenêtre de dialogue améliorée
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing
        
        $form = New-Object System.Windows.Forms.Form
        $form.Text = "Message de commit - Analyse d'impact"
        $form.Size = New-Object System.Drawing.Size(800, 650)
        $form.StartPosition = "CenterScreen"
        $form.Font = New-Object System.Drawing.Font("Consolas", 9)

        # Label principal
        $label = New-Object System.Windows.Forms.Label
        $label.Location = New-Object System.Drawing.Point(10, 10)
        $label.Size = New-Object System.Drawing.Size(760, 20)
        $label.Text = "Message de commit :"

        # TextBox pour le message
        $textBox = New-Object System.Windows.Forms.TextBox
        $textBox.Location = New-Object System.Drawing.Point(10, 35)
        $textBox.Size = New-Object System.Drawing.Size(760, 25)
        $textBox.Text = $suggestion
        $textBox.Font = New-Object System.Drawing.Font("Consolas", 10)
        $textBox.Select($suggestion.Length, 0)

        # Label pour le résumé
        $summaryLabel = New-Object System.Windows.Forms.Label
        $summaryLabel.Location = New-Object System.Drawing.Point(10, 70)
        $summaryLabel.Size = New-Object System.Drawing.Size(760, 20)
        $summaryLabel.Text = "Résumé des changements :"
        $summaryLabel.Font = New-Object System.Drawing.Font("Consolas", 9, [System.Drawing.FontStyle]::Bold)

        # TextBox pour afficher le résumé détaillé
        $summaryBox = New-Object System.Windows.Forms.TextBox
        $summaryBox.Location = New-Object System.Drawing.Point(10, 95)
        $summaryBox.Size = New-Object System.Drawing.Size(760, 100)
        $summaryBox.Multiline = $true
        $summaryBox.ScrollBars = "Vertical"
        $summaryBox.ReadOnly = $true
        $summaryBox.Text = ($summary -join "`r`n")
        $summaryBox.Font = New-Object System.Drawing.Font("Consolas", 9)

        # Label pour l'incidence
        $impactLabel = New-Object System.Windows.Forms.Label
        $impactLabel.Location = New-Object System.Drawing.Point(10, 205)
        $impactLabel.Size = New-Object System.Drawing.Size(760, 20)
        $impactLabel.Text = "Analyse d'incidence :"
        $impactLabel.Font = New-Object System.Drawing.Font("Consolas", 9, [System.Drawing.FontStyle]::Bold)
        $impactLabel.ForeColor = [System.Drawing.Color]::DarkBlue

        # TextBox pour l'analyse d'impact
        $impactBox = New-Object System.Windows.Forms.TextBox
        $impactBox.Location = New-Object System.Drawing.Point(10, 230)
        $impactBox.Size = New-Object System.Drawing.Size(760, 120)
        $impactBox.Multiline = $true
        $impactBox.ScrollBars = "Vertical"
        $impactBox.ReadOnly = $true
        
        $impactText = ""
        if ($criticalChanges.Count -gt 0) {
            $impactText += "=== CHANGEMENTS CRITIQUES ===`r`n"
            $impactText += ($criticalChanges -join "`r`n") + "`r`n`r`n"
        }
        if ($impacts.Count -gt 0) {
            $impactText += "=== ZONES IMPACTÉES ===`r`n"
            $impactText += ($impacts -join "`r`n") + "`r`n"
        }
        if ($uniqueComponents.Count -gt 0) {
            $impactText += "`r`n=== COMPOSANTS/MODULES AFFECTÉS ===`r`n"
            $impactText += "🔸 " + ($uniqueComponents -join "`r`n🔸 ")
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