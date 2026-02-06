"""
Script de test de connexion SAP Business One
"""
import asyncio
import os
import httpx
import json
from dotenv import load_dotenv

load_dotenv()

SAP_BASE_URL = os.getenv("SAP_REST_BASE_URL")
SAP_USER = os.getenv("SAP_USER")
SAP_PASSWORD = os.getenv("SAP_CLIENT_PASSWORD")
SAP_COMPANY = os.getenv("SAP_CLIENT")


async def test_sap_connection():
    print("=" * 50)
    print("TEST DE CONNEXION SAP BUSINESS ONE")
    print("=" * 50)
    print(f"\nURL: {SAP_BASE_URL}")
    print(f"Utilisateur: {SAP_USER}")
    print(f"Base de donnees: {SAP_COMPANY}")
    print("-" * 50)

    url = f"{SAP_BASE_URL}/Login"
    auth_payload = {
        "UserName": SAP_USER,
        "Password": SAP_PASSWORD,
        "CompanyDB": SAP_COMPANY
    }
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "curl/8.5.0"
    }

    try:
        async with httpx.AsyncClient(verify=False, http2=False, timeout=30.0) as client:
            print(f"\nConnexion a {url}...")
            response = await client.post(url, content=json.dumps(auth_payload), headers=headers)

            print(f"Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print("\n[OK] CONNEXION REUSSIE!")
                print(f"Session ID: {data.get('SessionId', 'N/A')}")
                print(f"Version SAP: {data.get('Version', 'N/A')}")

                # Test d'une requete simple
                print("\n--- Test de requete Items ---")
                cookies = response.cookies
                items_response = await client.get(
                    f"{SAP_BASE_URL}/Items?$top=1&$select=ItemCode,ItemName",
                    cookies=cookies
                )
                if items_response.status_code == 200:
                    items_data = items_response.json()
                    print(f"[OK] Requete Items reussie")
                    if items_data.get("value"):
                        item = items_data["value"][0]
                        print(f"Premier article: {item.get('ItemCode')} - {item.get('ItemName')}")
                else:
                    print(f"[ERREUR] Requete Items: {items_response.status_code}")

                # Logout
                await client.post(f"{SAP_BASE_URL}/Logout", cookies=cookies)
                print("\n[OK] Deconnexion effectuee")
                return True
            else:
                print(f"\n[ERREUR] Connexion echouee")
                print(f"Reponse: {response.text}")
                return False

    except httpx.ConnectError as e:
        print(f"\n[ERREUR] Impossible de se connecter au serveur SAP")
        print(f"Details: {e}")
        return False
    except httpx.TimeoutException:
        print(f"\n[ERREUR] Timeout - Le serveur ne repond pas")
        return False
    except Exception as e:
        print(f"\n[ERREUR] {type(e).__name__}: {e}")
        return False


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")  # Ignorer les warnings SSL

    result = asyncio.run(test_sap_connection())
    print("\n" + "=" * 50)
    print(f"RESULTAT: {'SUCCES' if result else 'ECHEC'}")
    print("=" * 50)
