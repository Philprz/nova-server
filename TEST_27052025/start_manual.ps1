# Démarrage manuel étape par étape pour diagnostic

param([switch]$Verbose)

$ErrorActionPreference = "Stop"

Write-Host "=== DÉMARRAGE MANUEL NOVA POUR DIAGNOSTIC ===" -ForegroundColor Cyan

# Étape 1: Vérifier le répertoire
$projectPath = $PSScriptRoot
Write-Host "1. Répertoire projet : $projectPath" -ForegroundColor Yellow
Set-Location -Path $projectPath

# Étape 2: Vérifier l'environnement virtuel
Write-Host "2. Activation environnement virtuel..." -ForegroundColor Yellow
$venvPath = Join-Path $projectPath "venv\Scripts\Activate.ps1"
if (Test-Path $venvPath) {
    . $venvPath
    Write-Host "   ✅ Environnement virtuel activé" -ForegroundColor Green
    Write-Host "   Python: $((python --version 2>&1).ToString())" -ForegroundColor Gray
} else {
    Write-Host "   ❌ Environnement virtuel non trouvé" -ForegroundColor Red
    exit 1
}

# Étape 3: Test des imports critiques
Write-Host "3. Test des imports Python..." -ForegroundColor Yellow
try {
    python -c "import fastapi, mcp, simple_salesforce, httpx; print('   ✅ Tous les imports OK')"
} catch {
    Write-Host "   ❌ Erreur d'import : $_" -ForegroundColor Red
    Write-Host "   Installation des dépendances manquantes..." -ForegroundColor Yellow
    pip install -r requirements.txt
}

# Étape 4: Test de connexion Salesforce
Write-Host "4. Test connexion Salesforce..." -ForegroundColor Yellow
try {
    $sfTest = python -c "
from dotenv import load_dotenv
import os
load_dotenv()
from simple_salesforce import Salesforce
sf = Salesforce(
    username=os.getenv('SALESFORCE_USERNAME'),
    password=os.getenv('SALESFORCE_PASSWORD'),
    security_token=os.getenv('SALESFORCE_SECURITY_TOKEN'),
    domain=os.getenv('SALESFORCE_DOMAIN', 'login')
)
result = sf.query('SELECT Id FROM Account LIMIT 1')
print('   ✅ Salesforce OK -', result['totalSize'], 'comptes trouvés')
" 2>&1
    Write-Host $sfTest -ForegroundColor Green
} catch {
    Write-Host "   ❌ Erreur Salesforce : $_" -ForegroundColor Red
}

# Étape 5: Test de connexion SAP
Write-Host "5. Test connexion SAP..." -ForegroundColor Yellow
try {
    $sapTest = python -c "
from dotenv import load_dotenv
import os, httpx, asyncio, json
load_dotenv()

async def test_sap():
    url = os.getenv('SAP_REST_BASE_URL') + '/Login'
    payload = {
        'UserName': os.getenv('SAP_USER'),
        'Password': os.getenv('SAP_CLIENT_PASSWORD'),
        'CompanyDB': os.getenv('SAP_CLIENT')
    }
    async with httpx.AsyncClient(verify=False) as client:
        response = await client.post(url, json=payload)
        if response.status_code == 200:
            print('   ✅ SAP OK - Connexion réussie')
        else:
            print(f'   ❌ SAP Erreur {response.status_code}: {response.text[:100]}')

asyncio.run(test_sap())
" 2>&1
    Write-Host $sapTest -ForegroundColor ($sapTest -match "✅" ? "Green" : "Red")
} catch {
    Write-Host "   ❌ Erreur SAP : $_" -ForegroundColor Red
}

# Étape 6: Démarrage FastAPI en mode verbeux
Write-Host "6. DÉMARRAGE FASTAPI..." -ForegroundColor Yellow
Write-Host "   URL d'accès : http://localhost:8000/" -ForegroundColor Cyan
Write-Host "   Swagger UI  : http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "   Démo devis  : http://localhost:8000/static/demo_devis.html" -ForegroundColor Cyan
Write-Host ""
Write-Host "Pour arrêter : Ctrl+C" -ForegroundColor Gray
Write-Host "=====================================`n" -ForegroundColor Gray

# Lancer FastAPI en mode synchrone pour voir les erreurs
uvicorn main:app --reload --host 0.0.0.0 --port 8000
