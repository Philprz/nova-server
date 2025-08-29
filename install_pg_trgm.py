#!/usr/bin/env python3
"""
Script d'installation extension PostgreSQL pg_trgm
Usage: python install_pg_trgm.py
"""

import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

def install_pg_trgm():
    """Installation extension pg_trgm pour PostgreSQL"""
    
    # Chargement variables d'environnement
    load_dotenv()
    
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL manquante dans .env")
        return False
    
    try:
        # Connexion PostgreSQL
        engine = create_engine(db_url)
        
        with engine.connect() as conn:
            print("✅ Connexion PostgreSQL établie")
            
            # Vérification extension existante
            result = conn.execute(text(
                "SELECT * FROM pg_extension WHERE extname = 'pg_trgm'"
            )).fetchone()
            
            if result:
                print("✅ Extension pg_trgm déjà installée")
                version = result.extversion if hasattr(result, 'extversion') else 'inconnue'
                print(f"   Version: {version}")
            else:
                print("⏳ Installation extension pg_trgm...")
                
                # Installation extension
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
                conn.commit()
                print("✅ Extension pg_trgm installée")
            
            # Test fonction similarity
            test_result = conn.execute(text(
                "SELECT similarity('imprimante', 'printer') as score"
            )).fetchone()
            
            if test_result:
                score = test_result.score
                print(f"✅ Test similarity: {score:.3f}")
                print("✅ Extension pg_trgm opérationnelle")
            else:
                print("❌ Test similarity échoué")
                return False
            
            # Vérification finale
            final_check = conn.execute(text(
                "SELECT extname, extversion FROM pg_extension WHERE extname = 'pg_trgm'"
            )).fetchone()
            
            if final_check:
                print(f"✅ Vérification finale: {final_check.extname} v{final_check.extversion}")
                return True
            else:
                print("❌ Vérification finale échouée")
                return False
                
    except Exception as e:
        print(f"❌ Erreur installation: {str(e)}")
        return False

def create_trgm_index():
    """Création index GIN pour optimiser recherches (optionnel)"""
    
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    
    try:
        engine = create_engine(db_url)
        
        with engine.connect() as conn:
            # Vérifier existence table produits_sap
            table_exists = conn.execute(text(
                "SELECT to_regclass('public.produits_sap')"
            )).scalar()
            
            if not table_exists:
                print("⚠️ Table produits_sap inexistante - Index ignoré")
                return False
            
            # Vérifier index existant
            index_exists = conn.execute(text(
                "SELECT 1 FROM pg_indexes WHERE tablename = 'produits_sap' AND indexdef LIKE '%gin_trgm_ops%'"
            )).fetchone()
            
            if index_exists:
                print("✅ Index GIN trigram déjà existant")
                return True
            
            print("⏳ Création index GIN pour recherche trigram...")
            
            # Création index (sans CONCURRENTLY dans transaction)
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_produits_sap_name_trgm ON produits_sap USING GIN (item_name gin_trgm_ops)"
            ))
            conn.commit()
            
            print("✅ Index GIN créé")
            return True
            
    except Exception as e:
        print(f"⚠️ Index GIN non créé: {str(e)}")
        return False

if __name__ == "__main__":
    print("=== Installation extension PostgreSQL pg_trgm ===")
    
    success = install_pg_trgm()
    
    if success:
        print("\n=== Création index optionnel ===")
        create_trgm_index()
        
        print("\n✅ Installation terminée avec succès")
        sys.exit(0)
    else:
        print("\n❌ Installation échouée")
        sys.exit(1)