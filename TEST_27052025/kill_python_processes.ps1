# Script pour tuer proprement tous les processus Python NOVA

Write-Host "=== NETTOYAGE DES PROCESSUS PYTHON ===" -ForegroundColor Yellow

# Trouver tous les processus Python
$pythonProcesses = Get-Process python -ErrorAction SilentlyContinue

if ($pythonProcesses) {
    Write-Host "Processus Python trouvés :" -ForegroundColor Cyan
    foreach ($process in $pythonProcesses) {
        $commandLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($process.Id)").CommandLine
        Write-Host "  PID $($process.Id): $commandLine" -ForegroundColor Gray
    }
    
    Write-Host "`nArrêt des processus..." -ForegroundColor Yellow
    foreach ($process in $pythonProcesses) {
        try {
            Stop-Process -Id $process.Id -Force
            Write-Host "  ✅ PID $($process.Id) arrêté" -ForegroundColor Green
        } catch {
            Write-Host "  ❌ Impossible d'arrêter PID $($process.Id): $_" -ForegroundColor Red
        }
    }
} else {
    Write-Host "Aucun processus Python trouvé" -ForegroundColor Green
}

# Attendre un peu
Start-Sleep -Seconds 2

# Vérifier qu'ils sont bien arrêtés
$remainingProcesses = Get-Process python -ErrorAction SilentlyContinue
if ($remainingProcesses) {
    Write-Host "`n⚠️ Processus Python encore actifs :" -ForegroundColor Yellow
    $remainingProcesses | Select-Object Id, ProcessName
} else {
    Write-Host "`n✅ Tous les processus Python ont été arrêtés" -ForegroundColor Green
}

Write-Host "`n=== NETTOYAGE TERMINÉ ===" -ForegroundColor Yellow