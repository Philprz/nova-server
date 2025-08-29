# Script PowerShell : fix_alembic_conflicts.ps1

# 1. Sauvegarde des migrations existantes
if (Test-Path "alembic/versions_backup") {
    Remove-Item "alembic/versions_backup" -Recurse -Force
}
Move-Item "alembic/versions" "alembic/versions_backup"

# 2. Recréation du dossier versions propre
New-Item -ItemType Directory -Path "alembic/versions" -Force
New-Item -ItemType File -Path "alembic/versions/__init__.py" -Force

# 3. Suppression de la table alembic_version pour reset
$env:PGPASSWORD = "spirit"
& psql -h localhost -U nova_user -d nova_mcp -c "DROP TABLE IF EXISTS alembic_version;"

# 4. Nouvelle migration initiale
alembic revision --autogenerate -m "create_produits_sap_table_clean"

# 5. Application de la migration
alembic upgrade head

Write-Host "Migration Alembic nettoyée et appliquée"