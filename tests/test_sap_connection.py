import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()
 
async def test_sap_connection():
    import os
    
    # Configuration
    SAP_BASE_URL = os.getenv("SAP_REST_BASE_URL")
    SAP_USER = os.getenv("SAP_USER")
    SAP_CLIENT_PASSWORD = os.getenv("SAP_CLIENT_PASSWORD") 
    SAP_CLIENT = os.getenv("SAP_CLIENT")
    
    print(f"Test connexion SAP: {SAP_BASE_URL}")
    
    # Authentification
    auth_payload = {
        "UserName": SAP_USER,
        "Password": SAP_CLIENT_PASSWORD,
        "CompanyDB": SAP_CLIENT
    }
    
    try:
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            response = await client.post(f"{SAP_BASE_URL}/Login", json=auth_payload)
            response.raise_for_status()
            print("✅ Connexion SAP réussie")
            return True
    except Exception as e:
        print(f"❌ Erreur connexion SAP: {str(e)}")
        return False

if __name__ == "__main__":
    asyncio.run(test_sap_connection())