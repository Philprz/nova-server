from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os
import sys

# Ajout du rÃ©pertoire parent au path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# Import tous les modèles pour Alembic autogenerate
from models.database_models import Base as DatabaseBase
from db.models import Base as DBBase
from models.user import User  # Modèle User MFA

# Utiliser db.models.Base pour la migration MFA
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = DBBase.metadata

def run_migrations_offline() -> None:
    """ExÃ©cute les migrations en mode 'offline' (sans connexion DB)."""
    url = config.get_main_option("sqlalchemy.url")  # âœ… corrigÃ©
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},  # âœ… corrigÃ©
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """ExÃ©cute les migrations en mode 'online' (avec connexion DB)."""
    configuration = config.get_section(config.config_ini_section) or {}
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",  # âœ… corrigÃ©
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
