import psycopg2
from psycopg2 import OperationalError
import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

def test_connexion_postgresql():
    """Test des différentes méthodes de connexion PostgreSQL"""
    
    print("=== TEST CONNEXION POSTGRESQL ===")
    
    # Configuration depuis .env
    db_url = os.getenv("DATABASE_URL", "postgresql://nova_user:spirit@localhost:5432/nova_mcp")
    print(f"URL depuis .env: {db_url}")
    
    # Extraction des paramètres
    # postgresql://nova_user:spirit@localhost:5432/nova_mcp
    parts = db_url.replace("postgresql://", "").split("@")
    user_pass = parts[0].split(":")
    host_db = parts[1].split("/")
    host_port = host_db[0].split(":")
    
    user = user_pass[0]
    password = user_pass[1] if len(user_pass) > 1 else ""
    host = host_port[0]
    port = host_port[1] if len(host_port) > 1 else "5432"
    database = host_db[1] if len(host_db) > 1 else "postgres"
    
    print(f"Paramètres extraits:")
    print(f"  User: {user}")
    print(f"  Password: {'*' * len(password)}")
    print(f"  Host: {host}")
    print(f"  Port: {port}")
    print(f"  Database: {database}")
    
    # Test 1: Connexion avec les paramètres .env
    print(f"\n1. Test avec utilisateur '{user}':")
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password
        )
        print("   ✅ CONNEXION RÉUSSIE !")
        conn.close()
        return True
    except OperationalError as e:
        print(f"   ❌ Erreur: {e}")
    
    # Test 2: Connexion avec postgres/postgres (défaut)
    print(f"\n2. Test avec utilisateur 'postgres' (mot de passe vide):")
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            database="postgres",
            user="postgres",
            password=""
        )
        print("   ✅ CONNEXION RÉUSSIE avec postgres!")
        conn.close()
        return True
    except OperationalError as e:
        print(f"   ❌ Erreur: {e}")
    
    # Test 3: Connexion avec postgres/postgres (mot de passe défaut)
    print(f"\n3. Test avec utilisateur 'postgres' (mot de passe 'postgres'):")
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            database="postgres",
            user="postgres",
            password="postgres"
        )
        print("   ✅ CONNEXION RÉUSSIE avec postgres/postgres!")
        conn.close()
        return True
    except OperationalError as e:
        print(f"   ❌ Erreur: {e}")
    
    print(f"\n❌ Aucune méthode de connexion n'a fonctionné.")
    print(f"💡 Solutions possibles:")
    print(f"   1. Réinitialiser le mot de passe postgres")
    print(f"   2. Modifier pg_hba.conf pour autoriser l'authentification 'trust'")
    print(f"   3. Créer l'utilisateur 'nova_user' avec le bon mot de passe")
    
    return False

if __name__ == "__main__":
    test_connexion_postgresql()