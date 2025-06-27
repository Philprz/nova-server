# reset_db.py
"""
Script pour réinitialiser complètement la base de données et Alembic
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.models import Base
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

def reset_database():
    """Réinitialise complètement la base de données"""
    
    # Charger les variables d'environnement
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        print("❌ DATABASE_URL non trouvé dans .env")
        return False
    
    try:
        # Créer le moteur SQLAlchemy
        engine = create_engine(database_url)
        
        print("🔄 Connexion à la base de données...")
        
        # Supprimer toutes les tables existantes
        with engine.connect() as conn:
            print("🗑️ Suppression de toutes les tables...")
            
            # Supprimer la table alembic_version
            conn.execute(text("DROP TABLE IF EXISTS alembic_version CASCADE"))
            
            # Supprimer toutes les tables métier
            conn.execute(text("DROP TABLE IF EXISTS interactions_llm CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS tickets CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS factures CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS utilisateurs CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS clients CASCADE"))
            
            # Valider les changements
            conn.commit()
            print("✅ Toutes les tables supprimées")
        
        # Recréer toutes les tables depuis les modèles
        print("🏗️ Création des tables depuis les modèles...")
        Base.metadata.create_all(engine)
        print("✅ Tables créées avec succès")
        
        # Supprimer les anciens fichiers de migration
        versions_dir = "alembic/versions"
        if os.path.exists(versions_dir):
            print("🗑️ Suppression des anciennes migrations...")
            for file in os.listdir(versions_dir):
                if file.endswith('.py') and file != '__init__.py':
                    file_path = os.path.join(versions_dir, file)
                    os.remove(file_path)
                    print(f"   Supprimé: {file}")
        
        print("✅ Base de données réinitialisée avec succès !")
        print("📝 Vous pouvez maintenant créer une nouvelle migration avec:")
        print("   python -m alembic revision --autogenerate -m 'Initial migration'")
        print("   python -m alembic upgrade head")
        
        return True
        
    except Exception as e:
        print(f"❌ Erreur lors de la réinitialisation: {str(e)}")
        return False

if __name__ == "__main__":
    print("🚀 Réinitialisation de la base de données NOVA")
    print("⚠️  Cette opération va supprimer TOUTES les données !")
    
    confirm = input("Voulez-vous continuer ? (oui/non): ").lower()
    if confirm in ['oui', 'o', 'yes', 'y']:
        if reset_database():
            sys.exit(0)
        else:
            sys.exit(1)
    else:
        print("❌ Opération annulée")
        sys.exit(1)