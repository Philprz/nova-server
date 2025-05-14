import asyncio
from services.mcp_connector import MCPConnector

async def test_salesforce_query():
    # Test avec une requête simple
    query = "SELECT Id, Name FROM Account LIMIT 5"
    result = await MCPConnector.call_salesforce_mcp("salesforce_query", {"query": query})
    print("Résultat de la requête Salesforce:")
    print(result)
    
    # Test avec le client spécifique
    client_name = "Edge Communications"
    query = f"SELECT Id, Name, AccountNumber FROM Account WHERE Name LIKE '%{client_name}%' LIMIT 1"
    result = await MCPConnector.call_salesforce_mcp("salesforce_query", {"query": query})
    print("\nRecherche du client:")
    print(result)

if __name__ == "__main__":
    asyncio.run(test_salesforce_query())