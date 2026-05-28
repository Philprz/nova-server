# models/database_models.py
from sqlalchemy import (
    Column, String, Float, Integer, Boolean, DateTime, Text,
    ForeignKey, JSON, create_engine,
)
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


# ===========================================================================
# Admin LLM dynamique : fournisseurs IA, configuration de routage, credentials
# Tables alimentees par l'interface admin (templates/admin_llm.html)
# ===========================================================================

class LLMProvider(Base):
    """Fournisseur LLM configure dynamiquement (Anthropic, OpenAI, Mistral, custom)."""
    __tablename__ = 'llm_providers'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    base_url = Column(String(500), nullable=False)
    api_format = Column(String(20), nullable=False)  # "anthropic" | "openai"
    api_key_encrypted = Column(Text, nullable=False)
    available_models = Column(JSON, nullable=False, default=list)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


class LLMConfiguration(Base):
    """Chaine ordonnee principal + fallbacks. priority=0 = principal."""
    __tablename__ = 'llm_configuration'

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider_id = Column(Integer, ForeignKey('llm_providers.id', ondelete='RESTRICT'), nullable=False, index=True)
    model_name = Column(String(200), nullable=False)
    priority = Column(Integer, nullable=False, index=True)
    is_enabled = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


class AdminCredentials(Base):
    """Mot de passe admin LLM + question/reponse de secours (hashes bcrypt)."""
    __tablename__ = 'admin_credentials'

    id = Column(Integer, primary_key=True, autoincrement=True)
    password_hash = Column(String(255), nullable=False)
    security_question = Column(String(500), nullable=False)
    security_answer_hash = Column(String(255), nullable=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

# Configuration base de données
DATABASE_URL = os.getenv('DATABASE_URL')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def create_tables():
    Base.metadata.create_all(bind=engine)
    print('Tables créées avec succès')

if __name__ == '__main__':
    create_tables()
