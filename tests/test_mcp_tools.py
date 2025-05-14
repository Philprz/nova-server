# test_mcp_tools.py
import asyncio
import json
import os
import sys
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Configuration de l'encodage
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

async def test_salesforce():
    """Teste les outils Salesforce"""
    print("\n=== TEST SALESFORCE MCP ===")
    
    try:
        from simple_salesforce import Salesforce
        
        # Connexion Salesforce
        username = os.getenv("SALESFORCE_USERNAME")
        password = os.getenv("SALESFORCE_PASSWORD")
        security_token = os.getenv("SALESFORCE_SECURITY_TOKEN")
        domain = os.getenv("SALESFORCE_DOMAIN", "login")
        
        print(f"Tentative de connexion Salesforce avec {username}...")
        
        sf = Salesforce(
            username=username,
            password=password,
            security_token=security_token,
            domain=domain
        )
        
        # Test de requête simple
        result = sf.query("SELECT Id, Name FROM Account LIMIT 2")
        
        print(f"✅ Connexion Salesforce réussie - {result.get('totalSize', 0)} comptes trouvés")
        if result.get('records'):
            for record in result['records']:
                print(f"  - {record.get('Name')} ({record.get('Id')})")
    except Exception as e:
        print(f"❌ Erreur Salesforce: {str(e)}")

async def test_sap():
    """Teste les outils SAP"""
    print("\n=== TEST SAP MCP ===")
    
    try:
        import httpx
        
        # Configuration SAP
        SAP_BASE_URL = os.getenv("SAP_REST_BASE_URL")
        SAP_USER = os.getenv("SAP_USER")
        SAP_CLIENT_PASSWORD = os.getenv("SAP_CLIENT_PASSWORD")
        SAP_CLIENT = os.getenv("SAP_CLIENT")
        
        print(f"Tentative de connexion SAP à {SAP_BASE_URL}...")
        
        # Authentification
        auth_payload = {
            "UserName": SAP_USER,
            "Password": SAP_CLIENT_PASSWORD,
            "CompanyDB": SAP_CLIENT
        }
        
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            response = await client.post(f"{SAP_BASE_URL}/Login", json=auth_payload)
            response.raise_for_status()
            
            print("✅ Connexion SAP réussie")
            
            # Test de lecture simple
            items_response = await client.get(f"{SAP_BASE_URL}/Items?$top=2", cookies=response.cookies)
            items_response.raise_for_status()
            
            items = items_response.json()
            print(f"✅ Lecture des articles réussie - {len(items.get('value', []))} articles trouvés")
            
            if items.get('value'):
                for item in items.get('value'):
                    print(f"  - {item.get('ItemName')} ({item.get('ItemCode')})")
    except Exception as e:
        print(f"❌ Erreur SAP: {str(e)}")

if __name__ == "__main__":
    print("=== TEST DES OUTILS MCP NOVA ===")
    
    # Exécuter les tests
    asyncio.run(test_salesforce())
    asyncio.run(test_sap())
    
    print("\n=== TESTS TERMINÉS ===")