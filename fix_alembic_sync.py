import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

def fix_alembic_version():
    """Synchronise la version Alembic en base avec les fichiers de migration"""
    
    # Connexion à la DB
    db_url = os.getenv("DATABASE_URL")
    parts = db_url.replace("postgresql://", "").split("@")
    user_pass = parts[0].split(":")
    host_db = parts[1].split("/")
    host_port = host_db[0].split(":")
    
    user = user_pass[0]
    password = user_pass[1]
    host = host_port[0]
    port = host_port[1] if len(host_port) > 1 else "5432"
    database = host_db[1].split("?")[0]  # Enlever les paramètres
    
    print("=== SYNCHRONISATION ALEMBIC ===")
    print(f"Connexion à {user}@{host}:{port}/{database}")
    
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password
        )
        cursor = conn.cursor()
        
        # Vérifier la version actuelle
        cursor.execute("SELECT version_num FROM alembic_version")
        current = cursor.fetchone()
        if current:
            print(f"Version actuelle en DB: {current[0]}")
        else:
            print("Aucune version trouvée en DB")
        
        # Mettre à jour vers la version head des fichiers
        new_version = "3119d069468b"  # Version dans alembic/versions/
        print(f"Mise à jour vers: {new_version}")
        
        if current:
            cursor.execute("UPDATE alembic_version SET version_num = %s", (new_version,))
        else:
            cursor.execute("INSERT INTO alembic_version (version_num) VALUES (%s)", (new_version,))
        
        conn.commit()
        print("✅ Version Alembic synchronisée !")
        
        # Vérification
        cursor.execute("SELECT version_num FROM alembic_version")
        updated = cursor.fetchone()
        print(f"Nouvelle version confirmée: {updated[0]}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return False

if __name__ == "__main__":
    if fix_alembic_version():
        print("\n🎯 Test de validation:")
        print("Exécutez: python -m alembic current")
    else:
        print("\n❌ Correction échouée")