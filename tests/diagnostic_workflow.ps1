# Script de diagnostic complet pour identifier le problème
# diagnostic_workflow.ps1

Write-Host "=== DIAGNOSTIC WORKFLOW NOVA ===" -ForegroundColor Cyan

# 1. Vérifier les logs du workflow
Write-Host "`n1. Vérification des logs récents..." -ForegroundColor Yellow
if (Test-Path "logs/workflow_devis.log") {
    Write-Host "Dernières 20 lignes du log workflow:" -ForegroundColor Green
    Get-Content "logs/workflow_devis.log" -Tail 20 | ForEach-Object { Write-Host "  $_" }
} else {
    Write-Host "❌ Fichier log workflow introuvable" -ForegroundColor Red
}

# 2. Vérifier les logs MCP
Write-Host "`n2. Vérification des logs MCP..." -ForegroundColor Yellow
if (Test-Path "logs/salesforce_mcp.log") {
    Write-Host "Dernières 10 lignes Salesforce MCP:" -ForegroundColor Green
    Get-Content "logs/salesforce_mcp.log" -Tail 10 | ForEach-Object { Write-Host "  SF: $_" }
}

if (Test-Path "logs/sap_mcp.log") {
    Write-Host "Dernières 10 lignes SAP MCP:" -ForegroundColor Green
    Get-Content "logs/sap_mcp.log" -Tail 10 | ForEach-Object { Write-Host "  SAP: $_" }
}

# 3. Tester les connexions
Write-Host "`n3. Test des connexions..." -ForegroundColor Yellow
Write-Host "Test Salesforce..." -ForegroundColor Gray
try {
    $sfResult = python -c "
import sys, os
sys.path.append('.')
import asyncio
from services.mcp_connector import MCPConnector

async def test():
    result = await MCPConnector.call_salesforce_mcp('salesforce_query', {'query': 'SELECT Id, Name FROM Account LIMIT 1'})
    print(f'SF: {result}')

asyncio.run(test())
"
    Write-Host "✅ Test Salesforce: $sfResult" -ForegroundColor Green
} catch {
    Write-Host "❌ Erreur test Salesforce: $_" -ForegroundColor Red
}

Write-Host "Test SAP..." -ForegroundColor Gray
try {
    $sapResult = python -c "
import sys, os
sys.path.append('.')
import asyncio
from services.mcp_connector import MCPConnector

async def test():
    result = await MCPConnector.call_sap_mcp('ping', {})
    print(f'SAP: {result}')

asyncio.run(test())
"
    Write-Host "✅ Test SAP: $sapResult" -ForegroundColor Green
} catch {
    Write-Host "❌ Erreur test SAP: $_" -ForegroundColor Red
}

# 4. Vérifier le dernier résultat de test
Write-Host "`n4. Recherche du dernier fichier de résultat..." -ForegroundColor Yellow
$resultFiles = Get-ChildItem -Path "." -Name "test_result_*.json" | Sort-Object -Descending
if ($resultFiles.Count -gt 0) {
    $latestResult = $resultFiles[0]
    Write-Host "Dernier fichier résultat: $latestResult" -ForegroundColor Green
    $content = Get-Content $latestResult | ConvertFrom-Json
    Write-Host "Statut: $($content.status)" -ForegroundColor $(if($content.status -eq 'success'){'Green'}else{'Red'})
    Write-Host "Message: $($content.message)" -ForegroundColor White
    if ($content.client) {
        Write-Host "Client: $($content.client.name)" -ForegroundColor White
    }
    if ($content.unavailable_products) {
        Write-Host "Produits indisponibles: $($content.unavailable_products.Count)" -ForegroundColor Yellow
    }
} else {
    Write-Host "❌ Aucun fichier de résultat trouvé" -ForegroundColor Red
}

# 5. Rechercher des erreurs spécifiques
Write-Host "`n5. Recherche d'erreurs spécifiques..." -ForegroundColor Yellow
if (Test-Path "logs/workflow_devis.log") {
    $errors = Select-String -Path "logs/workflow_devis.log" -Pattern "ERROR|Exception|Erreur" | Select-Object -Last 5
    if ($errors) {
        Write-Host "Dernières erreurs trouvées:" -ForegroundColor Red
        $errors | ForEach-Object { Write-Host "  ❌ $($_.Line)" -ForegroundColor Red }
    } else {
        Write-Host "✅ Aucune erreur récente trouvée" -ForegroundColor Green
    }
}

Write-Host "`n=== FIN DIAGNOSTIC ===" -ForegroundColor Cyan
Write-Host "Veuillez analyser les résultats ci-dessus pour identifier le problème." -ForegroundColor White