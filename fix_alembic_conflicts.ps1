# fix_alembic_conflicts_windows.ps1
# Script PowerShell pour Windows sans dépendance psql

# 1. Sauvegarde des migrations existantes
if (Test-Path "alembic/versions_backup") {
    Remove-Item "alembic/versions_backup" -Recurse -Force
}
if (Test-Path "alembic/versions") {
    Move-Item "alembic/versions" "alembic/versions_backup"
}

# 2. Recréation du dossier versions propre
New-Item -ItemType Directory -Path "alembic/versions" -Force
New-Item -ItemType File -Path "alembic/versions/__init__.py" -Force

# 3. Suppression table alembic_version via Python
python -c "
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv('DATABASE_URL')
engine = create_engine(db_url)

with engine.connect() as conn:
    conn.execute(text('DROP TABLE IF EXISTS alembic_version CASCADE;'))
    conn.commit()
    print('Table alembic_version supprimée')
"

# 4. Création du modèle SQLAlchemy si manquant
if (-not (Test-Path "models/database_models.py")) {
    New-Item -ItemType Directory -Path "models" -Force
    @"
# models/database_models.py
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()
Base = declarative_base()

class ProduitsSAP(Base):
    __tablename__ = 'produits_sap'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    item_code = Column(String(50), nullable=False, unique=True, index=True)
    item_name = Column(String(200), nullable=False)
    u_description = Column(String(500))
    avg_price = Column(Float, default=0.0)
    on_hand = Column(Integer, default=0)
    items_group_code = Column(String(20))
    manufacturer = Column(String(100))
    bar_code = Column(String(50))
    valid = Column(Boolean, default=True)
    sales_unit = Column(String(10), default='UN')
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

# Configuration base de données
DATABASE_URL = os.getenv('DATABASE_URL')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def create_tables():
    Base.metadata.create_all(bind=engine)
    print('Tables créées avec succès')

if __name__ == '__main__':
    create_tables()
"@ | Out-File -FilePath "models/database_models.py" -Encoding utf8
}

# 5. Mise à jour alembic/env.py
@"
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os
import sys

# Ajout du répertoire parent au path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from models.database_models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline() -> None:
    url = config.get_main_option(\"sqlalchemy.url\")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={\"paramstyle\": \"named\"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix=\"sqlalchemy.\",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
"@ | Out-File -FilePath "alembic/env.py" -Encoding utf8

# 6. Création migration initiale
alembic revision --autogenerate -m "create_produits_sap_table_initial"

# 7. Application migration
alembic upgrade head

Write-Host "Migration Alembic Windows terminée avec succès"