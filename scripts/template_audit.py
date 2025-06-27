# scripts/template_audit.py
import os
import sys
import asyncio

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Now we can safely import modules from the project
from services.mcp_connector import MCPConnector


async def audit_templates():
    """Audit des templates disponibles dans Salesforce et SAP"""
    
    print("🔍 AUDIT DES TEMPLATES DEVIS")
    print("=" * 50)
    
    # 1. Templates Salesforce
    print("\n📊 SALESFORCE - Templates Quote/Email")
    sf_templates = await MCPConnector.call_salesforce_mcp("salesforce_query", {
        "query": "SELECT Id, Name, Subject, Body FROM EmailTemplate WHERE Folder.Name LIKE '%Quote%' OR Name LIKE '%Devis%' OR Name LIKE '%Quote%'"
    })
    
    if sf_templates.get("records"):
        for template in sf_templates["records"]:
            print(f"  ✅ {template['Name']} (ID: {template['Id']})")
    else:
        print("  ❌ Aucun template email trouvé")
    
    # 2. Quote Templates Salesforce
    quote_templates = await MCPConnector.call_salesforce_mcp("salesforce_query", {
        "query": "SELECT Id, Name FROM QuoteTemplate"
    })
    
    if quote_templates.get("records"):
        for template in quote_templates["records"]:
            print(f"  ✅ Quote Template: {template['Name']} (ID: {template['Id']})")
    
    # 3. Vérifier SAP templates/formats
    print("\n📦 SAP - Formats de Devis Disponibles")
    sap_formats = await MCPConnector.call_sap_mcp("sap_read", {
        "endpoint": "/ReportLayouts?$filter=contains(LayoutName,'Quote') or contains(LayoutName,'Devis')",
        "method": "GET"
    })
    
    if "error" not in sap_formats and sap_formats.get("value"):
        for layout in sap_formats["value"]:
            print(f"  ✅ SAP Layout: {layout.get('LayoutName')}")
    else:
        print("  ℹ️ Utilisation du format standard SAP")

if __name__ == "__main__":
    asyncio.run(audit_templates())