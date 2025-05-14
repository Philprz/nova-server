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
    async def call_mcp_server(server_name, action, params):
        # Mode direct sans WebSocket - temporaire
        if server_name == "salesforce_mcp" and action == "salesforce_query":
            from services.salesforce import sf
            result = sf.query(params["query"])
            return result
        elif server_name == "sap_mcp":
            # Simulation SAP - à remplacer
            return {"success": True}
    
    @staticmethod
    async def _call_mcp(server_name: str, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Méthode générique pour appeler un outil MCP via subprocess (compatible stdio)
        
        Args:
            server_name: Nom du serveur MCP (ex: "salesforce_mcp", "sap_mcp")
            action: Nom de l'action MCP
            params: Paramètres de l'action
            
        Returns:
            Résultat de l'appel MCP
        """
        logger.info(f"Appel MCP: {server_name}.{action}")
        
        try:
            # Créer fichier temporaire pour les paramètres d'entrée
            with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as temp_in:
                temp_in_path = temp_in.name
                json.dump({"action": action, "params": params}, temp_in)
            
            # Créer fichier temporaire pour la sortie
            with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as temp_out:
                temp_out_path = temp_out.name
            
            try:
                # Exécuter le script avec les arguments appropriés
                script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), f"{server_name}.py")
                
                process = await asyncio.create_subprocess_exec(
                    sys.executable, script_path, 
                    "--input-file", temp_in_path,
                    "--output-file", temp_out_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    logger.error(f"Erreur exécution MCP: {stderr.decode()}")
                    return {"error": f"Échec appel MCP: code {process.returncode}"}
                
                # Lire le résultat depuis le fichier de sortie
                with open(temp_out_path, 'r') as f:
                    result = json.load(f)
                
                logger.info(f"Appel MCP réussi: {action}")
                return result
                
            except Exception as e:
                logger.error(f"Exception lors de l'appel MCP: {str(e)}")
                return {"error": str(e)}
            finally:
                # Nettoyer les fichiers temporaires
                if os.path.exists(temp_in_path):
                    os.unlink(temp_in_path)
                if os.path.exists(temp_out_path):
                    os.unlink(temp_out_path)
        
        except Exception as e:
            logger.error(f"Erreur critique: {str(e)}")
            return {"error": str(e)}