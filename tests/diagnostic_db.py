# diagnostic_db.py
"""
Script de diagnostic pour vérifier l'état de la base de données et d'Alembic
"""

import os
import sys
from sqlalchemy import create_engine, text, inspect
from dotenv import load_dotenv
from db.models import Base
import subprocess

def check_database_status():
    """Vérifie l'état de la base de données et d'Alembic"""
    
    print("🔍 DIAGNOSTIC DE LA BASE DE DONNÉES NOVA")
    print("=" * 50)
    
    # Charger les variables d'environnement
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        print("❌ DATABASE_URL non trouvé dans .env")
        return False
    
    print(f"📊 URL de base de données: {database_url}")
    
    try:
        # Créer le moteur SQLAlchemy
        engine = create_engine(database_url)
        inspector = inspect(engine)
        
        print("\n1️⃣ TABLES EXISTANTES DANS LA BASE DE DONNÉES:")
        print("-" * 45)
        
        existing_tables = inspector.get_table_names()
        if existing_tables:
            for table in sorted(existing_tables):
                print(f"   ✓ {table}")
        else:
            print("   ℹ️ Aucune table trouvée")
        
        print(f"\n   Total: {len(existing_tables)} table(s)")
        
        print("\n2️⃣ TABLES DÉFINIES DANS LES MODÈLES SQLALCHEMY:")
        print("-" * 48)
        
        model_tables = []
        for table_name in Base.metadata.tables:
            model_tables.append(table_name)
            print(f"   ✓ {table_name}")
        
        print(f"\n   Total: {len(model_tables)} table(s)")
        
        print("\n3️⃣ ANALYSE DE COHÉRENCE:")
        print("-" * 25)
        
        # Tables manquantes en base
        missing_in_db = set(model_tables) - set(existing_tables)
        if missing_in_db:
            print("   ❌ Tables définies dans les modèles mais absentes de la DB:")
            for table in missing_in_db:
                print(f"      - {table}")
        
        # Tables en base mais pas dans les modèles
        extra_in_db = set(existing_tables) - set(model_tables)
        if extra_in_db:
            print("   ⚠️ Tables présentes en DB mais non définies dans les modèles:")
            for table in extra_in_db:
                print(f"      - {table}")
        
        # Tables communes
        common_tables = set(existing_tables) & set(model_tables)
        if common_tables:
            print("   ✅ Tables synchronisées:")
            for table in common_tables:
                print(f"      - {table}")
        
        print("\n4️⃣ ÉTAT D'ALEMBIC:")
        print("-" * 18)
        
        # Vérifier la table alembic_version
        if "alembic_version" in existing_tables:
            with engine.connect() as conn:
                result = conn.execute(text("SELECT version_num FROM alembic_version"))
                current_version = result.fetchone()
                if current_version:
                    print(f"   ✓ Version Alembic actuelle: {current_version[0]}")
                else:
                    print("   ⚠️ Table alembic_version vide")
        else:
            print("   ❌ Table alembic_version non trouvée (Alembic non initialisé)")
        
        # Vérifier les fichiers de migration
        migrations_dir = "alembic/versions"
        if os.path.exists(migrations_dir):
            migration_files = [f for f in os.listdir(migrations_dir) if f.endswith('.py') and f != '__init__.py']
            print(f"   📁 Fichiers de migration trouvés: {len(migration_files)}")
            for migration_file in migration_files:
                print(f"      - {migration_file}")
        else:
            print("   ❌ Dossier alembic/versions non trouvé")
        
        print("\n5️⃣ RECOMMANDATIONS:")
        print("-" * 18)
        
        if not existing_tables and not missing_in_db:
            print("   🆕 SCÉNARIO: Base de données vide")
            print("   📋 Actions recommandées:")
            print("      1. Supprimer les migrations existantes vides")
            print("      2. Générer une migration initiale avec --autogenerate")
            print("      3. Appliquer la migration")
            
        elif missing_in_db and not extra_in_db:
            print("   🔄 SCÉNARIO: Modèles plus récents que la base")
            print("   📋 Actions recommandées:")
            print("      1. Générer une migration pour les tables manquantes")
            print("      2. Appliquer la migration")
            
        elif not missing_in_db and not extra_in_db and common_tables:
            print("   ✅ SCÉNARIO: Base et modèles synchronisés")
            print("   📋 Actions recommandées:")
            print("      1. Vérifier que la version Alembic correspond")
            print("      2. Tamponner la version actuelle si nécessaire")
            
        elif extra_in_db or missing_in_db:
            print("   ⚠️ SCÉNARIO: Incohérences détectées")
            print("   📋 Actions recommandées:")
            print("      1. Analyser les différences en détail")
            print("      2. Décider de la stratégie (réinitialisation vs migration)")
            
        print("\n" + "=" * 50)
        return True
        
    except Exception as e:
        print(f"❌ Erreur lors du diagnostic: {str(e)}")
        return False

def check_alembic_commands():
    """Teste les commandes Alembic de base"""
    print("\n6️⃣ TEST DES COMMANDES ALEMBIC:")
    print("-" * 30)
    
    try:
        # Test alembic current
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "current"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        
        if result.returncode == 0:
            print("   ✅ alembic current: OK")
            if result.stdout.strip():
                print(f"      Version: {result.stdout.strip()}")
            else:
                print("      Version: (aucune)")
        else:
            print("   ❌ alembic current: ERREUR")
            print(f"      {result.stderr}")
        
        # Test alembic history
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "history"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        
        if result.returncode == 0:
            print("   ✅ alembic history: OK")
            lines = result.stdout.strip().split('\n')
            print(f"      Migrations trouvées: {len([line for line in lines if line.strip()])}")
        else:
            print("   ❌ alembic history: ERREUR")
            print(f"      {result.stderr}")
            
    except Exception as e:
        print(f"   ❌ Erreur test Alembic: {str(e)}")

if __name__ == "__main__":
    print("🚀 Lancement du diagnostic de base de données")
    
    success = check_database_status()
    if success:
        check_alembic_commands()
        print("\n✅ Diagnostic terminé. Analysez les recommandations ci-dessus.")
    else:
        print("\n❌ Diagnostic échoué. Vérifiez la configuration de la base de données.")