Write-Host "=== DIAGNOSTIC POSTGRESQL ===" -ForegroundColor Yellow

# 1. Identifier tous les processus PostgreSQL
Write-Host "`n1. Processus PostgreSQL actifs:" -ForegroundColor Cyan
Get-Process postgres* -ErrorAction SilentlyContinue | Format-Table Name, Id, CPU, WorkingSet -AutoSize

# 2. Identifier tous les services PostgreSQL
Write-Host "`n2. Services PostgreSQL installés:" -ForegroundColor Cyan
Get-Service postgresql* -ErrorAction SilentlyContinue | Format-Table Name, Status, StartType -AutoSize

# 3. Vérifier qui utilise le port 5432
Write-Host "`n3. Utilisation du port 5432:" -ForegroundColor Cyan
netstat -ano | findstr :5432

# 4. Vérifier les installations PostgreSQL
Write-Host "`n4. Installations PostgreSQL détectées:" -ForegroundColor Cyan
$pgDirs = @(
    "C:\Program Files\PostgreSQL",
    "C:\Program Files (x86)\PostgreSQL"
)
foreach ($dir in $pgDirs) {
    if (Test-Path $dir) {
        Get-ChildItem $dir -Directory | ForEach-Object {
            Write-Host "   - Version: $($_.Name) dans $($_.FullName)" -ForegroundColor Green
        }
    }
}