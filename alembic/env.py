from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
from db.models import Base
import os
import sys

# === Accès aux modèles ===
sys.path.append(
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..')
    )
)

# ⚠️ Adapte ceci selon l’endroit exact de ton fichier de modèles
from db.models import Base  # ← MODIFIE si besoin (ex: from models import Base)

# === Configuration Alembic ===
config = context.config

# Setup logs
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata utilisée pour la génération automatique
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """Migrations en mode offline (sans connexion DB)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Migrations en mode online (avec connexion DB)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
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
