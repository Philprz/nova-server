# Script validation : test_db_connection.py

import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Ajout du répertoire parent au path
sys.path.append(str(Path(__file__).parent.parent))

load_dotenv()

def test_database_connection():
    """Test complet de la connexion et structure DB"""
    
    try:
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            print("❌ DATABASE_URL manquante dans .env")
            return False
            
        engine = create_engine(db_url)
        
        with engine.connect() as conn:
            # Test connexion
            print("✅ Connexion PostgreSQL établie")
            
            # Test existence table produits_sap
            result = conn.execute(text("SELECT to_regclass('public.produits_sap')")).scalar()
            if result:
                print("✅ Table produits_sap existe")
                
                # Compter les enregistrements
                count = conn.execute(text("SELECT COUNT(*) FROM produits_sap")).scalar()
                print(f"📊 Nombre de produits en base : {count}")
                
                return True
            else:
                print("❌ Table produits_sap n'existe pas")
                return False
                
    except Exception as e:
        print(f"❌ Erreur test DB : {str(e)}")
        return False

if __name__ == "__main__":
    success = test_database_connection()
    sys.exit(0 if success else 1)