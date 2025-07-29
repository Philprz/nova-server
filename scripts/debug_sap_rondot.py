# scripts/debug_sap_rondot.py - DIAGNOSTIC SAP RONDOT IMMÉDIAT
"""
Script pour diagnostiquer le problème SAP RONDOT
"""

import asyncio
import logging
import sys
import os
import json

# Ajouter le chemin du projet
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.mcp_connector import MCPConnector

# Configuration du logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def debug_sap_rondot():
    """Diagnostic complet SAP pour RONDOT"""
    print("=" * 80)
    print("DIAGNOSTIC SAP RONDOT - ANALYSE COMPLÈTE")
    print("=" * 80)
    
    connector = MCPConnector()
    
    # === TEST 1: sap_search RONDOT ===
    print("\n1. TEST sap_search - RONDOT")
    print("-" * 50)
    
    try:
        sap_search_result = await connector.call_mcp("sap_mcp", "sap_search", {
            "query": "RONDOT",
            "entity_type": "BusinessPartners",
            "limit": 10
        })
        
        print(f"Type de réponse: {type(sap_search_result)}")
        print(f"Clés disponibles: {list(sap_search_result.keys()) if isinstance(sap_search_result, dict) else 'N/A'}")
        print(f"Réponse complète:")
        print(json.dumps(sap_search_result, indent=2, default=str))
        
    except Exception as e:
        print(f"ERREUR sap_search: {e}")
    
    # === TEST 2: sap_read BusinessPartners ===
    print("\n\n2. TEST sap_read - BusinessPartners avec filter RONDOT")
    print("-" * 50)
    
    try:
        sap_read_result = await connector.call_mcp("sap_mcp", "sap_read", {
            "endpoint": "/BusinessPartners?$filter=contains(CardName,'RONDOT')&$top=10",
            "method": "GET"
        })
        
        print(f"Type de réponse: {type(sap_read_result)}")
        print(f"Clés disponibles: {list(sap_read_result.keys()) if isinstance(sap_read_result, dict) else 'N/A'}")
        print(f"Réponse complète:")
        print(json.dumps(sap_read_result, indent=2, default=str))
        
    except Exception as e:
        print(f"ERREUR sap_read: {e}")
    
    # === TEST 3: sap_read BusinessPartners avec LIKE ===
    print("\n\n3. TEST sap_read - BusinessPartners avec startswith")
    print("-" * 50)
    
    try:
        sap_read_like = await connector.call_mcp("sap_mcp", "sap_read", {
            "endpoint": "/BusinessPartners?$filter=startswith(CardName,'RON')&$top=10",
            "method": "GET"
        })
        
        print(f"Type de réponse: {type(sap_read_like)}")
        print(f"Clés disponibles: {list(sap_read_like.keys()) if isinstance(sap_read_like, dict) else 'N/A'}")
        print(f"Réponse complète:")
        print(json.dumps(sap_read_like, indent=2, default=str))
        
    except Exception as e:
        print(f"ERREUR sap_read startswith: {e}")
    
    # === TEST 4: Liste tous les BusinessPartners (premiers 10) ===
    print("\n\n4. TEST sap_read - Tous BusinessPartners (échantillon)")
    print("-" * 50)
    
    try:
        all_partners = await connector.call_mcp("sap_mcp", "sap_read", {
            "endpoint": "/BusinessPartners?$top=20",
            "method": "GET"
        })
        
        print(f"Type de réponse: {type(all_partners)}")
        if isinstance(all_partners, dict):
            print(f"Clés disponibles: {list(all_partners.keys())}")
            
            # Analyser la structure
            for key, value in all_partners.items():
                if isinstance(value, list) and value:
                    print(f"Clé '{key}' contient {len(value)} éléments")
                    if value:
                        print(f"Premier élément: {json.dumps(value[0], indent=2, default=str)[:200]}...")
                        # Chercher RONDOT dans cette liste
                        rondot_found = [item for item in value if 'RONDOT' in str(item).upper()]
                        if rondot_found:
                            print(f"🎯 RONDOT TROUVÉ dans '{key}': {len(rondot_found)} résultats")
                            for item in rondot_found:
                                print(f"   - {item.get('CardName', 'N/A')} (Code: {item.get('CardCode', 'N/A')})")
                        else:
                            print(f"   RONDOT non trouvé dans '{key}'")
        
    except Exception as e:
        print(f"ERREUR lecture tous BusinessPartners: {e}")
    
    # === RÉSUMÉ DIAGNOSTIC ===
    print("\n" + "=" * 80)
    print("RÉSUMÉ DIAGNOSTIC")
    print("=" * 80)
    
    print("\nVérifications à effectuer:")
    print("1. Structure exacte des réponses SAP")
    print("2. Présence de RONDOT dans les données")
    print("3. Clés utilisées par l'API SAP")
    print("4. Filtres OData fonctionnels")

if __name__ == "__main__":
    asyncio.run(debug_sap_rondot())