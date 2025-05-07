# check_dependencies.ps1
Write-Host "🔍 Vérification de l'environnement NOVA Middleware..." -ForegroundColor Cyan
. .\venv\Scripts\Activate.ps1

# Vérifier Python
$pythonVersion = python --version
Write-Host "Python: $pythonVersion" -ForegroundColor Yellow

# Vérifier MCP
try {
    $mcpVersion = mcp --version
    Write-Host "MCP: $mcpVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ MCP non installé ou inaccessible!" -ForegroundColor Red
}

# Vérifier les fichiers principaux
$files = @("server_mcp.py", "tools.py", "mcp_app.py", "server.yaml")
foreach ($file in $files) {
    if (Test-Path $file) {
        Write-Host "✅ $file existe" -ForegroundColor Green
    } else {
        Write-Host "❌ $file n'existe pas!" -ForegroundColor Red
    }
}

# Tester l'importation des modules clés
Write-Host "`n📦 Test d'importation des modules..." -ForegroundColor Cyan
$testImport = @"
try:
    from mcp_app import mcp
    print('✅ Import de mcp_app réussi')
except Exception as e:
    print(f'❌ Erreur lors de l\'import de mcp_app: {str(e)}')

try:
    from tools import salesforce_query, sap_read
    print('✅ Import de tools réussi')
except Exception as e:
    print(f'❌ Erreur lors de l\'import des outils: {str(e)}')

try:
    from services.exploration_salesforce import inspect_salesforce
    print('✅ Import des services d\'exploration réussi')
except Exception as e:
    print(f'❌ Erreur lors de l\'import des services d\'exploration: {str(e)}')
"@

$testImport | Out-File -FilePath "test_import.py" -Encoding utf8
python test_import.py
Remove-Item "test_import.py" -Force

Write-Host "`n🧪 Test de démarrage du serveur MCP (5 secondes)..." -ForegroundColor Cyan
$process = Start-Process -FilePath "python" -ArgumentList "server_mcp.py" -NoNewWindow -PassThru
Start-Sleep -Seconds 5
if (-not $process.HasExited) {
    Write-Host "✅ Le serveur MCP démarre correctement" -ForegroundColor Green
    Stop-Process -Id $process.Id -Force
} else {
    Write-Host "❌ Le serveur MCP s'est arrêté prématurément avec code $($process.ExitCode)" -ForegroundColor Red
}