# Créez un fichier test_db.py

from db.session import get_db, engine
from sqlalchemy import text

print('Tentative de connexion à la base de données...')
try:
    with engine.connect() as connection:
        result = connection.execute(text('SELECT 1'))
        print('✅ Connexion à la base de données réussie!')
        
    # Vérification des tables
    with engine.connect() as connection:
        result = connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
        tables = [row[0] for row in result]
        print(f'Tables disponibles: {tables}')
except Exception as e:
    print(f'❌ Erreur de connexion: {e}')

