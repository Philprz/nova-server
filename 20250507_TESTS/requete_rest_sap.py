import httpx

# URL de l'API pour le test de login
url = "http://localhost:8000/sap_login_test"

# En-têtes de la requête
headers = {
    "x-api-key": "ITS2025"
}

# Fonction pour tester la connexion
async def test_login():
    async with httpx.AsyncClient() as client:
        # Effectuer une requête GET
        response = await client.get(url, headers=headers)

        # Vérification du statut de la réponse
        if response.status_code == 200:
            print("Connexion réussie!")
            print("Réponse : ", response.json())  # Affiche la réponse JSON si disponible
        else:
            print(f"Erreur lors de la connexion, statut: {response.status_code}")
            print("Détails de l'erreur : ", response.text)

# Appel de la fonction
import asyncio
asyncio.run(test_login())
