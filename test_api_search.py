"""
Test rapide de l'API de recherche client
"""
import requests

try:
    print("Test de l'API de recherche client...")
    url = "http://localhost:8001/api/clients/search_clients"
    params = {"q": "Saverglass", "source": "sap", "limit": 10}

    print(f"Requête: GET {url}")
    print(f"Paramètres: {params}")

    response = requests.get(url, params=params, timeout=10)

    print(f"\nStatut: {response.status_code}")
    print(f"Réponse JSON:")
    print(response.json())

except requests.exceptions.Timeout:
    print("ERREUR: Timeout après 10 secondes")
except requests.exceptions.ConnectionError:
    print("ERREUR: Impossible de se connecter au backend")
except Exception as e:
    print(f"ERREUR: {e}")
