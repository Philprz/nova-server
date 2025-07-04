# Script de démonstration des capacités d'analyse intelligente
# Ce script simule différents types de modifications pour tester l'analyse

Write-Host "🤖 === DÉMONSTRATION ANALYSE INTELLIGENTE DE COMMITS ===" -ForegroundColor "Cyan"
Write-Host ""

# Simuler différents types de modifications
$testScenarios = @(
    @{
        'Type' = 'Bug Fix'
        'File' = 'auth.py'
        'AddedLines' = @(
            'try:',
            '    validate_token(token)',
            'except TokenExpiredError:',
            '    raise AuthenticationError("Token expired")'
        )
        'RemovedLines' = @(
            'if token:',
            '    # TODO: Add validation'
        )
    },
    @{
        'Type' = 'New Feature'
        'File' = 'api_routes.py'
        'AddedLines' = @(
            '@app.route("/api/clients/sync", methods=["POST"])',
            'def sync_clients():',
            '    """New endpoint for client synchronization"""',
            '    return handle_sync_request()'
        )
        'RemovedLines' = @()
    },
    @{
        'Type' = 'Refactoring'
        'File' = 'database.py'
        'AddedLines' = @(
            'def optimize_query(self, query):',
            '    """Optimized database query execution"""',
            '    return self.execute_with_cache(query)'
        )
        'RemovedLines' = @(
            'def old_query_method(self, query):',
            '    return self.execute(query)'
        )
    },
    @{
        'Type' = 'Configuration'
        'File' = 'config.json'
        'AddedLines' = @(
            '"database": {',
            '    "timeout": 30,',
            '    "pool_size": 10',
            '}'
        )
        'RemovedLines' = @(
            '"database": {',
            '    "timeout": 15',
            '}'
        )
    }
)

Write-Host "📋 Scénarios de test préparés :" -ForegroundColor "Yellow"
foreach ($scenario in $testScenarios) {
    Write-Host "   • $($scenario.Type) dans $($scenario.File)" -ForegroundColor "White"
}

Write-Host ""
Write-Host "🔍 Simulation de l'analyse intelligente..." -ForegroundColor "Cyan"
Write-Host ""

# Simuler l'analyse pour chaque scénario
foreach ($scenario in $testScenarios) {
    Write-Host "📁 Analyse de $($scenario.File):" -ForegroundColor "Green"
    
    # Simuler la détection de patterns
    $addedContent = $scenario.AddedLines -join ' '
    $removedContent = $scenario.RemovedLines -join ' '
    
    # Détection de bug fixes
    if ($addedContent -match 'try.*catch|exception|error|validate|fix|bug') {
        Write-Host "   🐛 Bug Fix détecté: Amélioration de la gestion d'erreurs" -ForegroundColor "Red"
        $suggestedCommit = "fix(auth): improve error handling and token validation"
    }
    # Détection de nouvelles fonctionnalités
    elseif ($addedContent -match 'def |function |@app\.route|endpoint|api') {
        Write-Host "   ✨ Nouvelle fonctionnalité détectée: Nouvel endpoint API" -ForegroundColor "Green"
        $suggestedCommit = "feat(api): add client synchronization endpoint"
    }
    # Détection de refactoring
    elseif ($addedContent -match 'optimize|improve|refactor' -and $removedContent.Length -gt 0) {
        Write-Host "   ♻️ Refactoring détecté: Optimisation de code" -ForegroundColor "Blue"
        $suggestedCommit = "refactor(db): optimize database query execution"
    }
    # Détection de configuration
    elseif ($scenario.File -match '\.(json|yaml|yml|xml|ini|conf|config|env)$') {
        Write-Host "   🔧 Modification de configuration détectée" -ForegroundColor "Magenta"
        $suggestedCommit = "config(db): update database connection settings"
    }
    
    Write-Host "   💡 Message suggéré: $suggestedCommit" -ForegroundColor "Yellow"
    Write-Host ""
}

Write-Host "🎯 === RÉSUMÉ DE LA DÉMONSTRATION ===" -ForegroundColor "Cyan"
Write-Host ""
Write-Host "✅ L'analyse intelligente peut détecter automatiquement :" -ForegroundColor "Green"
Write-Host "   • Les corrections de bugs (patterns d'erreur, validation)" -ForegroundColor "White"
Write-Host "   • Les nouvelles fonctionnalités (nouvelles fonctions, endpoints)" -ForegroundColor "White"
Write-Host "   • Le refactoring (optimisations, restructuration)" -ForegroundColor "White"
Write-Host "   • Les modifications de configuration" -ForegroundColor "White"
Write-Host ""
Write-Host "🚀 Votre script push_both.ps1 est maintenant INTELLIGENT !" -ForegroundColor "Green"
Write-Host "   Il analysera automatiquement vos modifications et générera" -ForegroundColor "White"
Write-Host "   des messages de commit précis et informatifs." -ForegroundColor "White"
Write-Host ""
Write-Host "📝 Pour tester, modifiez des fichiers et lancez :" -ForegroundColor "Yellow"
Write-Host "   .\push_both.ps1" -ForegroundColor "Cyan"