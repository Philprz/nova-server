"""
Configuration Alembic pour nova-server avec table produits_sap
"""

import os
import sys
from pathlib import Path
from alembic import context
from sqlalchemy import engine_from_config, pool, create_engine, MetaData, Table, Column, Integer, String, Boolean, DECIMAL, DateTime
from logging.config import fileConfig

# Ajout du répertoire parent au path
sys.path.append(str(Path(__file__).parent.parent))

# Configuration logging Alembic
if context.config.config_file_name is not None:
    fileConfig(context.config.config_file_name)

# Métadonnées SQLAlchemy avec définition table produits_sap
metadata = MetaData()

# Définition de la table produits_sap basée sur le script sync_sap_products.py
produits_sap_table = Table(
    'produits_sap',
    metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('item_code', String(50), nullable=False, unique=True, index=True),
    Column('item_name', String(255), nullable=False),
    Column('u_description', String(1000), nullable=True),
    Column('avg_price', DECIMAL(10, 2), nullable=False, default=0),
    Column('on_hand', Integer, nullable=False, default=0),
    Column('items_group_code', String(50), nullable=True),
    Column('manufacturer', String(255), nullable=True),
    Column('bar_code', String(100), nullable=True),
    Column('valid', Boolean, nullable=False, default=True),
    Column('sales_unit', String(10), nullable=False, default='UN'),
    Column('created_at', DateTime, nullable=False, server_default='CURRENT_TIMESTAMP'),
    Column('updated_at', DateTime, nullable=False, server_default='CURRENT_TIMESTAMP')
)

target_metadata = metadata

def run_migrations_offline():
    """Mode hors ligne"""
    url = context.config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    """Mode en ligne"""
    configuration = context.config.get_section(context.config.config_ini_section)
    configuration['sqlalchemy.url'] = os.getenv('DATABASE_URL', configuration['sqlalchemy.url'])
    
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, 
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()