# Script de vérification des services NOVA

Write-Host "=== VÉRIFICATION DES SERVICES NOVA ===" -ForegroundColor Cyan

# Fonction pour vérifier un port
function Test-Port {
    param([int]$Port)
    try {
        $connection = Test-NetConnection -ComputerName "localhost" -Port $Port -InformationLevel Quiet -WarningAction SilentlyContinue
        return $connection
    } catch {
        return $false
    }
}

# Vérifier les processus Python
Write-Host "1. Processus Python actifs :" -ForegroundColor Yellow
Get-Process python -ErrorAction SilentlyContinue | Select-Object Id, ProcessName, StartTime, @{Name='CommandLine';Expression={(Get-WmiObject Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine}}

Write-Host "`n2. Ports en écoute :" -ForegroundColor Yellow
Write-Host "   - Port 8000 (FastAPI) : " -NoNewline
if (Test-Port 8000) {
    Write-Host "✅ OUVERT" -ForegroundColor Green
} else {
    Write-Host "❌ FERME" -ForegroundColor Red
}

# Vérification des logs récents
Write-Host "`n3. Logs récents :" -ForegroundColor Yellow
$logFiles = @("logs\salesforce_mcp.log", "logs\sap_mcp.log")
foreach ($logFile in $logFiles) {
    if (Test-Path $logFile) {
        Write-Host "   - $logFile :" -ForegroundColor White
        Get-Content $logFile -Tail 3 | ForEach-Object { Write-Host "     $_" -ForegroundColor Gray }
    } else {
        Write-Host "   - $logFile : ❌ Fichier inexistant" -ForegroundColor Red
    }
}

# Test de connectivité FastAPI
Write-Host "`n4. Test FastAPI :" -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "http://localhost:8000/" -TimeoutSec 5
    Write-Host "   ✅ FastAPI répond : $($response.message)" -ForegroundColor Green
} catch {
    Write-Host "   ❌ FastAPI ne répond pas : $($_.Exception.Message)" -ForegroundColor Red
}

# Vérification environnement virtuel
Write-Host "`n5. Environnement virtuel :" -ForegroundColor Yellow
if ($env:VIRTUAL_ENV) {
    Write-Host "   ✅ Environnement virtuel actif : $env:VIRTUAL_ENV" -ForegroundColor Green
} else {
    Write-Host "   ❌ Environnement virtuel non actif" -ForegroundColor Red
}

Write-Host "`n=== FIN DE LA VÉRIFICATION ===" -ForegroundColor Cyan
