# tools/mcp_client.py

import os
import sys
import json
import argparse
import asyncio
import websockets
from dotenv import load_dotenv
# Ajouter le répertoire parent au chemin de recherche
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Importer le connecteur MCP
from services.mcp_connector import MCPConnector
# Charger les variables d'environnement
load_dotenv()

async def call_mcp_server(server_name, action, params):
    """
    Appelle un serveur MCP via WebSocket
    
    Args:
        server_name: Nom du serveur MCP
        action: Nom de l'action
        params: Paramètres de l'action
        
    Returns:
        Résultat de l'appel MCP
    """
    # Configurer l'URL du WebSocket selon le serveur
    if server_name == "salesforce_mcp":
        ws_url = os.getenv("SALESFORCE_MCP_WS_URL", "ws://localhost:8765")
    elif server_name == "sap_mcp":
        ws_url = os.getenv("SAP_MCP_WS_URL", "ws://localhost:8766")
    else:
        return {"error": f"Serveur MCP inconnu: {server_name}"}
    
    # Construire la requête MCP
    mcp_request = {
        "type": "request",
        "data": {
            "action": action,
            "parameters": params
        }
    }
    
    try:
        # Se connecter au serveur MCP
        async with websockets.connect(ws_url) as websocket:
            # Authentification si nécessaire
            auth_key = os.getenv("MCP_API_KEY", "ITS2025")
            await websocket.send(json.dumps({"type": "auth", "api_key": auth_key}))
            
            # Attendre la réponse d'authentification (capabilities)
            capabilities = await websocket.recv()
            
            # Envoyer la requête
            await websocket.send(json.dumps(mcp_request))
            
            # Recevoir la réponse
            response = await websocket.recv()
            return json.loads(response)
    except Exception as e:
        return {"error": f"Erreur de communication avec le serveur MCP: {str(e)}"}

def main():
    """Point d'entrée du script client MCP"""
    parser = argparse.ArgumentParser(description="Client MCP pour appels aux serveurs Claude")
    parser.add_argument("--server", required=True, help="Nom du serveur MCP (salesforce_mcp, sap_mcp)")
    parser.add_argument("--input", required=True, help="Chemin vers le fichier JSON d'entrée")
    
    args = parser.parse_args()
    
    try:
        # Lire le fichier d'entrée
        with open(args.input, "r") as f:
            input_data = json.load(f)
        
        action = input_data.get("action")
        params = input_data.get("params", {})
        
        if not action:
            print(json.dumps({"error": "Action MCP manquante"}))
            sys.exit(1)
        
        # Appeler le serveur MCP
        result = asyncio.run(call_mcp_server(args.server, action, params))
        
        # Afficher le résultat sur stdout (sera capturé par le processus appelant)
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()