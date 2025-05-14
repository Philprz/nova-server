# services/mcp_connector.py

import os
import json
import asyncio
import subprocess
import tempfile
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger("mcp_connector")

class MCPConnector:
    """Connecteur pour les appels MCP (Model Context Protocol)"""
    
    @staticmethod
    async def call_salesforce_mcp(action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Appelle un outil MCP Salesforce
        
        Args:
            action: Nom de l'action MCP (ex: "salesforce_query")
            params: Paramètres de l'action
            
        Returns:
            Résultat de l'appel MCP
        """
        return await MCPConnector._call_mcp("salesforce_mcp", action, params)
    
    @staticmethod
    async def call_sap_mcp(action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Appelle un outil MCP SAP
        
        Args:
            action: Nom de l'action MCP (ex: "sap_get_product_details")
            params: Paramètres de l'action
            
        Returns:
            Résultat de l'appel MCP
        """
        return await MCPConnector._call_mcp("sap_mcp", action, params)
    
    @staticmethod
    async def _call_mcp(server_name: str, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Méthode générique pour appeler un outil MCP
        
        Args:
            server_name: Nom du serveur MCP (ex: "salesforce_mcp", "sap_mcp")
            action: Nom de l'action MCP
            params: Paramètres de l'action
            
        Returns:
            Résultat de l'appel MCP
        """
        logger.info(f"Appel MCP: {server_name}.{action}")
        
        try:
            # En production, on utiliserait WebSockets ou autre protocole pour 
            # communiquer avec le serveur MCP. Pour le POC, on va simuler un appel.
            
            # Option 1: Utiliser un processus Python dédié
            # Créer un fichier temporaire pour les paramètres
            with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as temp:
                temp_path = temp.name
                json.dump({"action": action, "params": params}, temp)
            
            try:
                # Appeler un script Python dédié qui communique avec le serveur MCP
                process = await asyncio.create_subprocess_exec(
                    "python", "tools/mcp_client.py", 
                    "--server", server_name,
                    "--input", temp_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    logger.error(f"Erreur lors de l'appel MCP: {stderr.decode()}")
                    return {"error": f"Échec de l'appel MCP: {stderr.decode()}"}
                
                # Analyser la sortie JSON
                result = json.loads(stdout.decode())
                return result
            finally:
                # Nettoyer le fichier temporaire
                os.unlink(temp_path)
            
            # Option 2: Pour le POC, simuler les résultats
            # if server_name == "salesforce_mcp" and action == "salesforce_query":
            #     if "Account" in params.get("query", ""):
            #         return {"records": [{"Id": "001X", "Name": "ACME Corp"}]}
            # elif server_name == "sap_mcp" and action == "sap_get_product_details":
            #     return {"ItemCode": params.get("item_code"), "Price": 100.0}
            
            # return {"error": "Non implémenté dans le POC"}
        except Exception as e:
            logger.error(f"Erreur lors de l'appel MCP: {str(e)}")
            return {"error": str(e)}