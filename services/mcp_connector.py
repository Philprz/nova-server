# services/mcp_connector.py

import os
import sys
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
        """Appelle un outil MCP SAP"""
        return await MCPConnector._call_mcp("sap_mcp", action, params)

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
        """Méthode générique pour appeler un outil MCP via subprocess"""
        logger.info(f"Appel MCP: {server_name}.{action}")
        
        try:
            # Créer fichier temporaire pour les paramètres d'entrée
            with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as temp_in:
                temp_in_path = temp_in.name
                json.dump({"action": action, "params": params}, temp_in)
                temp_in.flush()
            
            # Créer fichier temporaire pour la sortie
            with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as temp_out:
                temp_out_path = temp_out.name
            
            try:
                # Exécuter le script avec les arguments appropriés
                script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), f"{server_name}.py")
                logger.info(f"Chemin du script MCP: {script_path}")
                
                if not os.path.exists(script_path):
                    logger.error(f"Script MCP introuvable: {script_path}")
                    return {"error": f"Script MCP introuvable: {script_path}"}
                
                # SOLUTION: Utiliser subprocess.run() dans un thread séparé plutôt que create_subprocess_exec
                import subprocess
                import concurrent.futures
                
                # Définir la fonction qui exécute subprocess.run
                def run_subprocess():
                    try:
                        result = subprocess.run(
                            [sys.executable, script_path, "--input-file", temp_in_path, "--output-file", temp_out_path],
                            capture_output=True,
                            text=True,
                            check=False
                        )
                        return result.returncode, result.stdout, result.stderr
                    except Exception as e:
                        logger.error(f"Erreur lors de l'exécution du subprocess: {e}")
                        return -1, "", str(e)
                
                # Exécuter dans un ThreadPoolExecutor pour éviter de bloquer la boucle asyncio
                loop = asyncio.get_event_loop()
                returncode, stdout, stderr = await loop.run_in_executor(
                    None, run_subprocess
                )
                
                logger.info(f"Sortie stdout: {stdout}")
                
                if returncode != 0:
                    logger.error(f"Erreur exécution MCP: {stderr}")
                    return {"error": f"Échec appel MCP: code {returncode}. Erreur: {stderr}"}
                
                # Lire le résultat depuis le fichier de sortie
                if os.path.exists(temp_out_path):
                    try:
                        with open(temp_out_path, 'r') as f:
                            result = json.load(f)
                        
                        logger.info(f"Appel MCP réussi: {action}")
                        return result
                    except json.JSONDecodeError as je:
                        logger.error(f"Erreur JSON dans le fichier de sortie: {je}")
                        with open(temp_out_path, 'r') as f:
                            content = f.read()
                        logger.error(f"Contenu brut: {content}")
                        return {"error": f"Format JSON invalide dans la réponse MCP: {je}"}
                else:
                    logger.error(f"Fichier de sortie inexistant: {temp_out_path}")
                    return {"error": "Fichier de sortie MCP non créé"}
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                logger.error(f"Exception lors de l'appel MCP: {str(e)}\n{tb}")
                return {"error": str(e)}
            finally:
                # Nettoyer les fichiers temporaires
                for path in [temp_in_path, temp_out_path]:
                    if os.path.exists(path):
                        try:
                            os.unlink(path)
                        except:
                            pass
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"Erreur critique: {str(e)}\n{tb}")
            return {"error": str(e)}