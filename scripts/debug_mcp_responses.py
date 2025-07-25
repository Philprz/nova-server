# scripts/debug_mcp_responses.py
"""
Script de debug pour analyser les réponses MCP brutes et identifier le problème
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
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def debug_mcp_responses():
    """Debug complet des réponses MCP"""
    print("=" * 80)
    print("DEBUG: ANALYSE DES RÉPONSES MCP BRUTES")
    print("=" * 80)
    
    connector = MCPConnector()
    
    # === TEST 1: SALESFORCE QUERY SIMPLE ===
    print("\n1. TEST SALESFORCE - Query simple")
    print("-" * 50)
    
    sf_query = "SELECT Id, Name, AccountNumber FROM Account LIMIT 3"
    sf_result = await connector.call_mcp("salesforce_mcp", "salesforce_query", {"query": sf_query})
    
    print(f"Type de réponse: {type(sf_result)}")
    print(f"Clés disponibles: {list(sf_result.keys()) if isinstance(sf_result, dict) else 'N/A'}")
    print(f"Contenu complet:")
    print(json.dumps(sf_result, indent=2, default=str)[:1000] + "..." if len(str(sf_result)) > 1000 else json.dumps(sf_result, indent=2, default=str))
    
    # === TEST 2: SALESFORCE RECHERCHE RONDOT ===
    print("\n2. TEST SALESFORCE - Recherche RONDOT")
    print("-" * 50)
    
    sf_rondot_query = "SELECT Id, Name, AccountNumber FROM Account WHERE Name LIKE '%Rondot%' LIMIT 5"
    sf_rondot_result = await connector.call_mcp("salesforce_mcp", "salesforce_query", {"query": sf_rondot_query})
    
    print(f"Type de réponse: {type(sf_rondot_result)}")
    print(f"Clés disponibles: {list(sf_rondot_result.keys()) if isinstance(sf_rondot_result, dict) else 'N/A'}")
    
    # Analyse détaillée des données
    if isinstance(sf_rondot_result, dict):
        if "records" in sf_rondot_result:
            records = sf_rondot_result["records"]
            print(f"Nombre de records: {len(records)}")
            if records:
                print(f"Premier record: {records[0]}")
        elif "data" in sf_rondot_result:
            data = sf_rondot_result["data"]
            print(f"Données dans 'data': {len(data) if isinstance(data, list) else 'N/A'}")
        elif "error" in sf_rondot_result:
            print(f"ERREUR: {sf_rondot_result['error']}")
        else:
            print("Aucun champ standard trouvé")
    
    # === TEST 3: SAP LECTURE SIMPLE ===
    print("\n3. TEST SAP - Lecture simple")
    print("-" * 50)
    
    sap_result = await connector.call_mcp("sap_mcp", "sap_read", {
        "endpoint": "/BusinessPartners?$top=3",
        "method": "GET"
    })
    
    print(f"Type de réponse: {type(sap_result)}")
    print(f"Clés disponibles: {list(sap_result.keys()) if isinstance(sap_result, dict) else 'N/A'}")
    print(f"Contenu complet:")
    print(json.dumps(sap_result, indent=2, default=str)[:1000] + "..." if len(str(sap_result)) > 1000 else json.dumps(sap_result, indent=2, default=str))
    
    # === TEST 4: SAP RECHERCHE RONDOT ===
    print("\n4. TEST SAP - Recherche RONDOT")
    print("-" * 50)
    
    sap_search_result = await connector.call_mcp("sap_mcp", "sap_search", {
        "query": "Rondot",
        "entity_type": "BusinessPartners",
        "limit": 5
    })
    
    print(f"Type de réponse: {type(sap_search_result)}")
    print(f"Clés disponibles: {list(sap_search_result.keys()) if isinstance(sap_search_result, dict) else 'N/A'}")
    
    # Analyse détaillée des données
    if isinstance(sap_search_result, dict):
        if "results" in sap_search_result:
            results = sap_search_result["results"]
            print(f"Nombre de results: {len(results) if isinstance(results, list) else 'N/A'}")
            if isinstance(results, list) and results:
                print(f"Premier result: {results[0]}")
        elif "value" in sap_search_result:
            value = sap_search_result["value"]
            print(f"Données dans 'value': {len(value) if isinstance(value, list) else 'N/A'}")
        elif "data" in sap_search_result:
            data = sap_search_result["data"]
            print(f"Données dans 'data': {len(data) if isinstance(data, list) else 'N/A'}")
        elif "error" in sap_search_result:
            print(f"ERREUR: {sap_search_result['error']}")
        else:
            print("Aucun champ standard trouvé")
    
    # === RÉSUMÉ ET DIAGNOSTIC ===
    print("\n" + "=" * 80)
    print("DIAGNOSTIC")
    print("=" * 80)
    
    print("\nSalesforce:")
    if isinstance(sf_rondot_result, dict):
        if "records" in sf_rondot_result and sf_rondot_result["records"]:
            print(f"  ✅ RONDOT trouvé: {len(sf_rondot_result['records'])} résultats")
            for record in sf_rondot_result["records"]:
                print(f"     - {record.get('Name')} (ID: {record.get('Id')})")
        else:
            print(f"  ❌ RONDOT non trouvé ou structure inattendue")
    
    print("\nSAP:")
    if isinstance(sap_search_result, dict):
        data_key = None
        data = None
        
        if "results" in sap_search_result:
            data_key = "results"
            data = sap_search_result["results"]
        elif "value" in sap_search_result:
            data_key = "value"
            data = sap_search_result["value"]
        elif "data" in sap_search_result:
            data_key = "data"
            data = sap_search_result["data"]
        
        if data and isinstance(data, list) and data:
            print(f"  ✅ RONDOT trouvé: {len(data)} résultats (clé: {data_key})")
            for client in data:
                card_name = client.get('CardName', client.get('Name', 'N/A'))
                card_code = client.get('CardCode', client.get('Code', 'N/A'))
                print(f"     - {card_name} (Code: {card_code})")
        else:
            print(f"  ❌ RONDOT non trouvé ou structure inattendue")
    
    # === RECOMMANDATIONS ===
    print("\n" + "=" * 80)
    print("RECOMMANDATIONS POUR CORRECTION")
    print("=" * 80)
    
    print("\n1. Modifier client_lister.py pour:")
    
    # Analyse Salesforce
    if isinstance(sf_rondot_result, dict) and "records" in sf_rondot_result:
        print("   - Salesforce: Utiliser la clé 'records' (CORRECT)")
    elif isinstance(sf_rondot_result, dict):
        available_keys = [k for k in sf_rondot_result.keys() if isinstance(sf_rondot_result[k], list)]
        if available_keys:
            print(f"   - Salesforce: Utiliser la clé '{available_keys[0]}' au lieu de 'records'")
    
    # Analyse SAP
    if isinstance(sap_search_result, dict):
        if "results" in sap_search_result:
            print("   - SAP: Utiliser la clé 'results' pour sap_search")
        elif "value" in sap_search_result:
            print("   - SAP: Utiliser la clé 'value' pour sap_search")
        elif "data" in sap_search_result:
            print("   - SAP: Utiliser la clé 'data' pour sap_search")
    
    print("\n2. Vérifier la logique de détection d'erreur:")
    print("   - Ne pas considérer l'absence de 'success': True comme une erreur")
    print("   - Vérifier explicitement 'error' in result ou success: False")

if __name__ == "__main__":
    asyncio.run(debug_mcp_responses())