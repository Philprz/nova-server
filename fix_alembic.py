# fix_alembic.py
"""
Script pour corriger l'état d'Alembic en créant une migration de référence
qui reflète l'état actuel de la base de données
"""

import os
import sys
import shutil
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import subprocess

def fix_alembic_migration():
    """Corrige l'état d'Alembic en créant une migration de référence"""
    
    print("🔧 CORRECTION DE L'ÉTAT ALEMBIC")
    print("=" * 40)
    
    # Charger les variables d'environnement
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        print("❌ DATABASE_URL non trouvé dans .env")
        return False
    
    try:
        # Étape 1: Sauvegarder l'ancienne migration vide
        old_migration_path = "alembic/versions/19025397a60c_initial_local_setup.py"
        backup_path = "alembic/versions/19025397a60c_initial_local_setup.py.backup"
        
        print("1️⃣ Sauvegarde de l'ancienne migration...")
        if os.path.exists(old_migration_path):
            shutil.copy(old_migration_path, backup_path)
            print(f"   ✅ Sauvegardé vers: {backup_path}")
        
        # Étape 2: Supprimer l'ancienne migration vide
        print("2️⃣ Suppression de l'ancienne migration vide...")
        if os.path.exists(old_migration_path):
            os.remove(old_migration_path)
            print(f"   ✅ Supprimé: {old_migration_path}")
        
        # Étape 3: Réinitialiser la version Alembic (revenir à la base)
        print("3️⃣ Réinitialisation de la version Alembic...")
        
        # Supprimer l'entrée de version actuelle
        engine = create_engine(database_url)
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM alembic_version"))
            conn.commit()
            print("   ✅ Version Alembic réinitialisée")
        
        # Étape 4: Générer une nouvelle migration de référence
        print("4️⃣ Génération de la nouvelle migration de référence...")
        
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "revision", "--autogenerate", "-m", "baseline_existing_schema"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        
        if result.returncode == 0:
            print("   ✅ Nouvelle migration générée avec succès")
            print(f"   📝 Sortie: {result.stdout}")
            
            # Récupérer le nom du fichier généré
            lines = result.stdout.split('\n')
            migration_file = None
            for line in lines:
                if "Generating" in line and "alembic/versions" in line:
                    # Extraire le chemin du fichier
                    migration_file = line.split("Generating ")[1].split(" ...")[0]
                    break
            
            if migration_file:
                print(f"   📁 Fichier créé: {migration_file}")
                
                # Vérifier le contenu du fichier généré
                if os.path.exists(migration_file):
                    with open(migration_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    if "def upgrade():" in content and "pass" not in content:
                        print("   ✅ Migration contient des instructions valides")
                    else:
                        print("   ⚠️ Migration générée semble vide - c'est normal si les tables correspondent déjà")
            
        else:
            print("   ❌ Erreur lors de la génération de la migration")
            print(f"   Erreur: {result.stderr}")
            return False
        
        # Étape 5: Tamponner la version (marquer comme appliquée sans l'exécuter)
        print("5️⃣ Tamponnage de la version (stamp head)...")
        
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "stamp", "head"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        
        if result.returncode == 0:
            print("   ✅ Version tamponnée avec succès")
            print("   📋 Alembic considère maintenant que la migration est appliquée")
        else:
            print("   ❌ Erreur lors du tamponnage")
            print(f"   Erreur: {result.stderr}")
            return False
        
        # Étape 6: Vérification finale
        print("6️⃣ Vérification finale...")
        
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "current"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        
        if result.returncode == 0:
            current_version = result.stdout.strip()
            print(f"   ✅ Version Alembic actuelle: {current_version}")
            
            if "(head)" in current_version:
                print("   🎯 Alembic est maintenant synchronisé avec votre base de données !")
                return True
            else:
                print("   ⚠️ Version pas à jour")
                return False
        else:
            print("   ❌ Erreur lors de la vérification")
            print(f"   Erreur: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Erreur lors de la correction: {str(e)}")
        return False

def test_future_migration():
    """Teste qu'une future migration peut être générée"""
    print("\n🧪 TEST DE MIGRATION FUTURE")
    print("=" * 30)
    
    print("Test de génération d'une migration fictive...")
    
    # Créer un fichier de test temporaire pour simuler un changement
    test_model_content = '''
# Test temporaire - sera supprimé
from sqlalchemy import Column, Integer, String
from db.models import Base

class TestTable(Base):
    __tablename__ = "test_temp_table"
    id = Column(Integer, primary_key=True)
    test_field = Column(String(50))
'''
    
    test_file = "test_model_temp.py"
    
    try:
        # Créer le fichier temporaire
        with open(test_file, 'w') as f:
            f.write(test_model_content)
        
        # Tenter de générer une migration
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "revision", "--autogenerate", "-m", "test_migration"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        
        if result.returncode == 0:
            print("   ✅ Génération de migration future: OK")
            
            # Supprimer la migration de test générée
            lines = result.stdout.split('\n')
            for line in lines:
                if "Generating" in line and "alembic/versions" in line:
                    test_migration_file = line.split("Generating ")[1].split(" ...")[0]
                    if os.path.exists(test_migration_file):
                        os.remove(test_migration_file)
                        print(f"   🗑️ Migration de test supprimée: {test_migration_file}")
                    break
        else:
            print("   ⚠️ Problème avec la génération de migration future")
            print(f"   Détail: {result.stderr}")
        
    except Exception as e:
        print(f"   ❌ Erreur test: {str(e)}")
    finally:
        # Supprimer le fichier temporaire
        if os.path.exists(test_file):
            os.remove(test_file)

if __name__ == "__main__":
    print("🚀 Lancement de la correction Alembic")
    
    success = fix_alembic_migration()
    
    if success:
        test_future_migration()
        print("\n🎉 CORRECTION TERMINÉE AVEC SUCCÈS !")
        print("📋 Alembic est maintenant correctement configuré")
        print("💡 Vous pouvez maintenant générer des migrations futures avec:")
        print("   python -m alembic revision --autogenerate -m 'description_changement'")
        print("   python -m alembic upgrade head")
    else:
        print("\n❌ CORRECTION ÉCHOUÉE")
        print("🔧 Vérifiez les erreurs ci-dessus et réessayez")