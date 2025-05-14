import asyncio
from websockets import connect
import json

# Configuration
WS_URL = "ws://178.33.233.120:8000/mcp"
API_KEY = "ITS2025"

async def test_mcp():
    async with connect(WS_URL) as websocket:
        # Authentification
        await websocket.send(json.dumps({"type": "auth", "api_key": API_KEY}))
        print("✅ Connecté au serveur MCP (auth envoyé).")

        # Réception des capacités du serveur
        capabilities = await websocket.recv()
        print("📨 Capabilities reçues :")
        print(json.dumps(json.loads(capabilities), indent=2))

        # Requête Salesforce
        mcp_request_salesforce = {
            "type": "request",
            "data": {
                "action": "salesforce.query",
                "parameters": {
                    "query": "SELECT Id, Name FROM Account LIMIT 3"
                }
            }
        }
        await websocket.send(json.dumps(mcp_request_salesforce))
        print("📤 Requête Salesforce envoyée.")

        # Réception de la réponse Salesforce
        response_salesforce = await websocket.recv()
        print("📥 Réponse Salesforce reçue :")
        print(json.dumps(json.loads(response_salesforce), indent=2))

        # Requête SAP
        mcp_request_sap = {
            "type": "request",
            "data": {
                "action": "sap.read",
                "parameters": {
                    "endpoint": "/Items",
                    "method": "GET"
                }
            }
        }
        await websocket.send(json.dumps(mcp_request_sap))
        print("📤 Requête SAP envoyée.")

        # Réception de la réponse SAP
        response_sap = await websocket.recv()
        print("📥 Réponse SAP reçue :")
        print(json.dumps(json.loads(response_sap), indent=2))

# Lancer l'event loop
if __name__ == "__main__":
    asyncio.run(test_mcp())
