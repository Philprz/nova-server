import requests
import json
import os

# Configuration
api_key = os.getenv("ANTHROPIC_API_KEY")  # Récupère la clé depuis les variables d'environnement
headers = {
    "x-api-key": api_key,
    "anthropic-version": "2023-06-01",
    "content-type": "application/json"
}

# Requête
url = "https://api.anthropic.com/v1/messages"
payload = {
    "model": "claude-3-opus-20240229",
    "max_tokens": 1000,
    "messages": [
        {"role": "user", "content": "Résume le projet NOVA en 3 points clés."}
    ]
}

# Exécution
response = requests.post(url, headers=headers, json=payload)
result = response.json()

# Affichage du résultat
if response.status_code == 200:
    print("Statut: Succès")
    print(f"Contenu: {result['content'][0]['text']}")
else:
    print(f"Erreur: {response.status_code}")
    print(f"Message: {result.get('error', {}).get('message', 'Inconnu')}")