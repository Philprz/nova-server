import aiohttp
import asyncio
import json

async def test_api():
    # URL de l'API
    url = "http://localhost:8000/generate_quote"
    
    # Données de la requête
    data = {
        "prompt": "faire un devis sur la fourniture de 500 ref A00001 pour le client Edge Communications",
        "draft_mode": False
    }
    
    # En-têtes
    headers = {
        "Content-Type": "application/json",
        "x-api-key": "ITS2025"
    }
    
    # Appel à l'API
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data, headers=headers) as response:
            result = await response.json()
            
            print(f"Statut de la réponse: {response.status}")
            print("Corps de la réponse:")
            print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(test_api())