import asyncio
from services.mcp_connector import MCPConnector

async def test_direct_account():
    account_id = "001gL000005OYCDQA4"
    query = f"SELECT Id, Name, AccountNumber FROM Account WHERE Id = '{account_id}'"
    
    print(f"Exécution de la requête: {query}")
    result = await MCPConnector.call_salesforce_mcp("salesforce_query", {"query": query})
    
    print("\nRésultat:")
    print(result)
    
    if result.get("totalSize", 0) > 0:
        print("\nCompte trouvé:")
        print(f"Nom: {result['records'][0]['Name']}")
        print(f"ID: {result['records'][0]['Id']}")
        print(f"Numéro de compte: {result['records'][0].get('AccountNumber', 'Non défini')}")
    else:
        print("\nAucun compte trouvé avec cet ID.")

if __name__ == "__main__":
    asyncio.run(test_direct_account())