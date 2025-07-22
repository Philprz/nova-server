# Test rapide des champs Account disponibles
# Fichier: test_salesforce_fields.py

import asyncio
from services.mcp_connector import MCPConnector

async def test_available_fields():
    """Test champs disponibles dans Account"""
    
    connector = MCPConnector()
    
    # Test 1: Requête minimale
    print("🔍 Test requête minimale...")
    query1 = "SELECT Id, Name FROM Account LIMIT 1"
    result1 = await connector.call_salesforce_mcp("salesforce_query", {"query": query1})
    print(f"Résultat basique: {result1.get('records', [])[:1]}")
    
    # Test 2: Champs de base
    print("\n🔍 Test champs standards...")
    query2 = """
        SELECT Id, Name, AccountNumber, Phone,
               BillingCity, BillingCountry, Type,
               Industry, CreatedDate
        FROM Account LIMIT 1
    """
    result2 = await connector.call_salesforce_mcp("salesforce_query", {"query": query2})
    print(f"Champs standards: {result2.get('records', [])[:1]}")
    
    # Test 3: Inspection objet
    print("\n🔍 Inspection structure Account...")
    inspect_result = await connector.call_salesforce_mcp("salesforce_inspect_object", {"object_name": "Account"})
    
    if inspect_result.get("fields"):
        available_fields = [f["name"] for f in inspect_result["fields"] if not f["name"].startswith("_")][:20]
        print(f"Champs disponibles (premiers 20): {available_fields}")
    
    return True

if __name__ == "__main__":
    asyncio.run(test_available_fields())
    