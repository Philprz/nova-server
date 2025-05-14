# test_salesforce_connection.py
import os
import sys
from dotenv import load_dotenv
from simple_salesforce import Salesforce

# Forcer l'encodage de sortie Ã  UTF-8
sys.stdout.reconfigure(encoding='utf-8')

# Charger les variables d'environnement
load_dotenv()

def test_connection():
    try:
        # RÃ©cupÃ©rer les informations de connexion
        username = os.getenv("SALESFORCE_USERNAME")
        password = os.getenv("SALESFORCE_PASSWORD")
        security_token = os.getenv("SALESFORCE_SECURITY_TOKEN")
        domain = os.getenv("SALESFORCE_DOMAIN", "login")
        
        print(f"Connexion avec {username} sur {domain}...")
        
        # Tenter la connexion
        sf = Salesforce(
            username=username,
            password=password,
            security_token=security_token,
            domain=domain
        )
        
        # Tester une requÃªte simple
        result = sf.query("SELECT Id, Name FROM Account LIMIT 5")
        
        print("Connexion reussie!")
        print(f"Comptes trouves: {len(result['records'])}")
        
        for record in result['records']:
            print(f" - {record['Name']} ({record['Id']})")
        
        return True
    except Exception as e:
        print(f"Erreur: {str(e)}")
        return False

if __name__ == "__main__":
    test_connection()
