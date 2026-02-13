# Script pour redemarrer le tunnel Cloudflare
Write-Host "Redemarrage du tunnel Cloudflare..." -ForegroundColor Cyan

# Verifier les services cloudflared disponibles
$services = Get-Service | Where-Object {$_.Name -like '*cloudflare*' -or $_.DisplayName -like '*cloudflare*'}

if ($services) {
    foreach ($service in $services) {
        Write-Host "Redemarrage du service: $($service.DisplayName)" -ForegroundColor Yellow
        try {
            Restart-Service $service.Name -Force
            Write-Host "Service redemarre avec succes" -ForegroundColor Green
        } catch {
            Write-Host "Erreur: $_" -ForegroundColor Red
            Write-Host ""
            Write-Host "Executez ce script en tant qu'administrateur:" -ForegroundColor Cyan
            Write-Host "   1. Clic droit sur PowerShell" -ForegroundColor White
            Write-Host "   2. 'Executer en tant qu'administrateur'" -ForegroundColor White
            Write-Host "   3. cd C:\Users\PPZ\NOVA-SERVER" -ForegroundColor White
            Write-Host "   4. .\restart-cloudflare-tunnel.ps1" -ForegroundColor White
        }
    }
} else {
    Write-Host "Aucun service Cloudflare trouve" -ForegroundColor Red
    Write-Host ""
    Write-Host "Verifiez que cloudflared est installe comme service:" -ForegroundColor Yellow
    Write-Host "  cloudflared service install" -ForegroundColor White
}

Write-Host ""
Write-Host "Configuration actuelle du tunnel:" -ForegroundColor Cyan
Get-Content C:\Users\PPZ\.cloudflared\config.yml
