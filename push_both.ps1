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
        # Récupérer les fichiers modifiés pour suggérer un message
        $changedFiles = git diff --name-only
        $suggestion = ""
        
        # Construire une suggestion basée sur les fichiers modifiés (max 3 fichiers)
        if ($changedFiles) {
            $fileList = ($changedFiles | Select-Object -First 3) -join ", "
            $moreFilesCount = ($changedFiles | Measure-Object).Count - 3
            
            $suggestion = "Modification de $fileList"
            if ($moreFilesCount -gt 0) {
                $suggestion += " et $moreFilesCount autres fichiers"
            }
        } else {
            $suggestion = "Update POC NOVA"
        }
        
        # Pré-remplir et permettre la modification de la suggestion
        Add-Type -AssemblyName System.Windows.Forms
        $form = New-Object System.Windows.Forms.Form
        $form.Text = "Message de commit"
        $form.Size = New-Object System.Drawing.Size(600, 200)
        $form.StartPosition = "CenterScreen"

        $textBox = New-Object System.Windows.Forms.TextBox
        $textBox.Location = New-Object System.Drawing.Point(10, 50)
        $textBox.Size = New-Object System.Drawing.Size(560, 20)
        $textBox.Text = $suggestion
        $textBox.Select($suggestion.Length, 0) # Positionner le curseur à la fin du texte

        $label = New-Object System.Windows.Forms.Label
        $label.Location = New-Object System.Drawing.Point(10, 20)
        $label.Size = New-Object System.Drawing.Size(560, 20)
        $label.Text = "Modifiez le message de commit si nécessaire :"

        $okButton = New-Object System.Windows.Forms.Button
        $okButton.Location = New-Object System.Drawing.Point(240, 100)
        $okButton.Size = New-Object System.Drawing.Size(100, 30)
        $okButton.Text = "OK"
        $okButton.DialogResult = [System.Windows.Forms.DialogResult]::OK
        $form.AcceptButton = $okButton

        $form.Controls.Add($textBox)
        $form.Controls.Add($label)
        $form.Controls.Add($okButton)
        $form.Topmost = $true

        $result = $form.ShowDialog()

        if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
            $CommitMessage = $textBox.Text
        } else {
            $CommitMessage = $suggestion # Si l'utilisateur ferme la fenêtre sans cliquer sur OK
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