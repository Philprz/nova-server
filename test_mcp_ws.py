import asyncio
import websockets
import json

# Configuration
WS_URL = "ws://178.33.233.120:8000/mcp"
API_KEY = "ITS2025"

async def test_mcp():
    # Connexion avec header x-api-key
    async with websockets.connect(
        WS_URL,
        extra_headers={"x-api-key": API_KEY}
    ) as websocket:

        print("✅ Connecté au serveur MCP.")

        # Réception du handshake capabilities
        capabilities = await websocket.recv()
        print("📨 Capabilities reçues :")
        print(json.dumps(json.loads(capabilities), indent=2))

        # Construction d'une requête MCP simple (ex: Salesforce query)
        mcp_request = {
            "type": "request",
            "data": {
                "action": "salesforce.query",
                "parameters": {
                    "query": "SELECT Id, Name FROM Account LIMIT 3"
                }
            }
        }

        # Envoi de la requête
        await websocket.send(json.dumps(mcp_request))
        print("📤 Requête envoyée.")

        # Réception de la réponse
        response = await websocket.recv()
        print("📥 Réponse reçue :")
        print(json.dumps(json.loads(response), indent=2))

# Lancer l'event loop
if __name__ == "__main__":
    asyncio.run(test_mcp())
