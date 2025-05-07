import requests

url = "http://localhost:8000/salesforce_query"
headers = {
    "x-api-key": "ITS2025"
}
body = {
    "query": "SELECT Name FROM Account LIMIT 1"
}

response = requests.post(url, headers=headers, json=body)

# Vérifier si la requête a réussi
if response.status_code == 200:
    print("Réponse:", response.json())  # Affiche la réponse JSON de l'API
else:
    print("Erreur:", response.status_code, response.text)
