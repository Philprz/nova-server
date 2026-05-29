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


# ===========================================================================
# Benchmark LLM : jeu de cas tests, sessions de comparaison, résultats
# ===========================================================================

class BenchmarkCase(Base):
    """Email test avec sortie attendue (ground truth) pour comparaison LLM."""
    __tablename__ = 'benchmark_cases'

    id = Column(Integer, primary_key=True, autoincrement=True)
    label = Column(String(200), nullable=False)
    email_content = Column(Text, nullable=False)
    expected_output = Column(JSON, nullable=False)
    # expected_output = {"client": "Nom Client", "products": [{"code": "REF", "name": "...", "quantity": N}]}
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


class BenchmarkRun(Base):
    """Session de comparaison : quels LLMs ont été testés, quand."""
    __tablename__ = 'benchmark_runs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    label = Column(String(200), nullable=True)
    llm_entries = Column(JSON, nullable=False)
    # llm_entries = [{"provider_id": 1, "provider_name": "Anthropic", "model_name": "claude-sonnet-4-6"}]
    case_ids = Column(JSON, nullable=False)
    # case_ids = [1, 2, 3]  ids des BenchmarkCase inclus dans ce run
    status = Column(String(20), nullable=False, default='pending')
    # status: pending | running | completed | error
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class BenchmarkResult(Base):
    """Résultat d'un LLM sur un cas test dans une session donnée."""
    __tablename__ = 'benchmark_results'

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey('benchmark_runs.id', ondelete='CASCADE'),
                    nullable=False, index=True)
    case_id = Column(Integer, ForeignKey('benchmark_cases.id', ondelete='CASCADE'),
                     nullable=False, index=True)
    provider_id = Column(Integer, ForeignKey('llm_providers.id', ondelete='SET NULL'),
                         nullable=True, index=True)
    provider_name = Column(String(100), nullable=False)
    model_name = Column(String(200), nullable=False)
    raw_response = Column(Text, nullable=True)
    parsed_response = Column(JSON, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    # Scores automatiques (0.0 à 1.0)
    score_json_valid = Column(Float, nullable=True)
    score_client_match = Column(Float, nullable=True)
    score_product_recall = Column(Float, nullable=True)
    score_product_precision = Column(Float, nullable=True)
    score_qty_accuracy = Column(Float, nullable=True)
    score_global = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


# Configuration base de données
DATABASE_URL = os.getenv('DATABASE_URL')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def create_tables():
    Base.metadata.create_all(bind=engine)
    print('Tables créées avec succès')

if __name__ == '__main__':
    create_tables()
