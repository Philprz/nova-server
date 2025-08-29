# script_reset_alembic.bat
@echo off
echo =====  RESET ALEMBIC COMPLET =====

echo Suppression historique migrations...
rmdir /s /q alembic\versions
mkdir alembic\versions
echo. > alembic\versions\__init__.py

echo Suppression table alembic_version...
psql -d nova_mcp -U nova_user -c "DROP TABLE IF EXISTS alembic_version;"

echo Création migration initiale...
alembic revision --autogenerate -m "initial_migration_with_produits_sap"

echo Application migration...
alembic upgrade head

echo =====  RESET TERMINÉ =====
pause