"""
Script d'initialisation de la base de données pour le système 2FA
Crée les tables et un utilisateur de test
"""

import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from db.models import Base
from models.user import User
from core.security import get_password_hash
import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Configuration de la base de données
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://nova_user:spirit@localhost:5432/nova_mcp")

print("=" * 60)
print("  Initialisation de la base de donnees NOVA - Systeme 2FA")
print("=" * 60)
print()

# Créer l'engine
print(f"[*] Connexion a la base de donnees...")
print(f"    URL: {DATABASE_URL.split('@')[1]}")  # Masquer les credentials
engine = create_engine(DATABASE_URL)

# Tester la connexion
try:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("[OK] Connexion reussie !")
except Exception as e:
    print(f"[ERREUR] Erreur de connexion: {e}")
    sys.exit(1)

print()

# Créer toutes les tables
print("[*] Creation des tables...")

try:
    # Importer tous les modèles pour qu'ils soient enregistrés
    from models.user import User

    # Créer les tables
    Base.metadata.create_all(bind=engine)
    print("[OK] Tables creees avec succes !")

    # Afficher les tables créées
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
        """))
        tables = [row[0] for row in result]

        if tables:
            print(f"\n[*] Tables dans la base de donnees:")
            for table in tables:
                print(f"    - {table}")
        else:
            print("\n[WARNING] Aucune table trouvee")

except Exception as e:
    print(f"[ERREUR] Erreur lors de la creation des tables: {e}")
    sys.exit(1)

print()

# Créer une session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

try:
    # Vérifier si l'utilisateur existe déjà
    existing_user = db.query(User).filter(User.email == "p.perez@it-spirit.com").first()

    if existing_user:
        print("[INFO] L'utilisateur p.perez@it-spirit.com existe deja")
        print(f"    ID: {existing_user.id}")
        print(f"    Username: {existing_user.username}")
        print(f"    TOTP active: {existing_user.is_totp_enabled}")
        print(f"    MFA obligatoire: {existing_user.mfa_enforced}")
    else:
        # Créer un utilisateur de test
        print("[*] Creation d'un utilisateur de test...")

        test_user = User(
            email="p.perez@it-spirit.com",
            username="p.perez",
            hashed_password=get_password_hash("31021225"),
            full_name="Pierre Perez",
            is_active=True,
            is_superuser=False,
            is_totp_enabled=False,  # Pas encore configuré
            mfa_enforced=True,      # MFA obligatoire
        )

        db.add(test_user)
        db.commit()
        db.refresh(test_user)

        print("[OK] Utilisateur cree avec succes !")
        print(f"    Email: {test_user.email}")
        print(f"    Password: 31021225")
        print(f"    Username: {test_user.username}")
        print(f"    ID: {test_user.id}")

    print()

    # Vérifier si d'autres utilisateurs existent
    total_users = db.query(User).count()
    print(f"[*] Nombre total d'utilisateurs: {total_users}")

    if total_users > 1:
        print("\n[*] Autres utilisateurs:")
        other_users = db.query(User).filter(User.email != "p.perez@it-spirit.com").all()
        for user in other_users:
            print(f"    - {user.email} (ID: {user.id}, TOTP: {user.is_totp_enabled})")

except Exception as e:
    print(f"[ERREUR] Erreur lors de la creation de l'utilisateur: {e}")
    db.rollback()
    sys.exit(1)
finally:
    db.close()

print()
print("=" * 60)
print("  [OK] Initialisation terminee avec succes !")
print("=" * 60)
print()
print("[*] Prochaines etapes:")
print("    1. Demarrer le serveur: python main.py")
print("    2. Ouvrir l'interface web: http://localhost:8200/demo/2fa")
print("    3. Se connecter avec:")
print("       - Email: p.perez@it-spirit.com")
print("       - Password: 31021225")
print()
print("[*] Documentation:")
print("    - Guide complet: DEMO_2FA_GUIDE.md")
print("    - Lancer la demo: LANCER_DEMO.md")
print("    - API Swagger: http://localhost:8200/docs")
print()
