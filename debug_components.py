import os
from dotenv import load_dotenv
import sys

load_dotenv()

def test_salesforce():
    try:
        from simple_salesforce import Salesforce
        sf = Salesforce(
            username=os.getenv("SALESFORCE_USERNAME"),
            password=os.getenv("SALESFORCE_PASSWORD"),
            security_token=os.getenv("SALESFORCE_SECURITY_TOKEN"),
            domain=os.getenv("SALESFORCE_DOMAIN", "login")
        )
        print("✅ Connexion Salesforce OK")
        result = sf.query("SELECT Id, Name FROM Account LIMIT 1")
        print(f"✅ Query Salesforce OK: {result}")
    except Exception as e:
        print(f"❌ Erreur Salesforce: {str(e)}")

def test_sap():
    try:
        import httpx
        print("✅ Import httpx OK")
    except Exception as e:
        print(f"❌ Erreur import httpx: {str(e)}")

def test_mcp():
    try:
        from mcp.server.fastmcp import FastMCP
        test_mcp = FastMCP("test")
        print("✅ Import FastMCP OK")
    except Exception as e:
        print(f"❌ Erreur FastMCP: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "salesforce":
            test_salesforce()
        elif sys.argv[1] == "sap":
            test_sap()
        elif sys.argv[1] == "mcp":
            test_mcp()
    else:
        print("Usage: python debug_components.py [salesforce|sap|mcp]")