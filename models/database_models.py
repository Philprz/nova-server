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
