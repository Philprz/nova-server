# services/parallel_connector.py - NOUVEAU
import asyncio
from typing import List, Dict, Any

class ParallelConnector:
    """Connecteur parallèle pour performances"""
    
    async def parallel_mcp_calls(self, calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Exécution parallèle des appels MCP"""
        tasks = []
        
        for call in calls:
            if call["server"] == "sap":
                task = MCPConnector.call_sap_mcp(call["action"], call["params"])
            elif call["server"] == "salesforce":
                task = MCPConnector.call_salesforce_mcp(call["action"], call["params"])
            else:
                continue
            tasks.append(task)
        
        # Exécution parallèle
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results
    
    async def get_client_and_products_parallel(self, client_name: str, product_codes: List[str]) -> Dict[str, Any]:
        """Récupération client + produits en parallèle"""
        calls = [
            {"server": "salesforce", "action": "salesforce_query", 
             "params": {"query": f"SELECT * FROM Account WHERE Name LIKE '%{client_name}%'"}},
            {"server": "sap", "action": "sap_search", 
             "params": {"query": client_name, "entity_type": "BusinessPartners"}}
        ]
        
        # Ajout des produits
        for code in product_codes:
            calls.append({
                "server": "sap", 
                "action": "sap_get_product_details",
                "params": {"item_code": code}
            })
        
        results = await self.parallel_mcp_calls(calls)
        
        return {
            "client_sf": results[0] if len(results) > 0 else None,
            "client_sap": results[1] if len(results) > 1 else None,
            "products": results[2:] if len(results) > 2 else []
        }
