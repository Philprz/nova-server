"""
Script pour intégrer la gestion des devis dans l'application principale
"""

import os

print("🔧 Configuration de l'intégration de la gestion des devis...")

# Contenu à ajouter dans main.py
integration_code = '''
# Import des routes de gestion des devis
try:
    from quote_management.api_routes import router as quote_management_router
    app.include_router(quote_management_router)
    print("✅ Routes de gestion des devis intégrées")
except ImportError as e:
    print(f"⚠️ Impossible d'importer les routes de gestion des devis: {e}")

# Route pour l'interface de gestion des devis
@app.get("/quote-management")
async def quote_management_interface():
    """Interface de gestion des devis SAP/Salesforce"""
    return FileResponse("quote_management/quote_management_interface.html")
'''

print("\n📝 Instructions pour intégrer la gestion des devis:\n")
print("1. Ajouter ces imports en haut du fichier main.py:")
print("   from quote_management.api_routes import router as quote_management_router")
print("   from fastapi.responses import FileResponse")
print("\n2. Ajouter cette ligne après les autres app.include_router():")
print("   app.include_router(quote_management_router)")
print("\n3. Ajouter cette route pour l'interface web:")
print("   @app.get('/quote-management')")
print("   async def quote_management_interface():")
print("       return FileResponse('quote_management/quote_management_interface.html')")
print("\n4. Ajouter au fichier salesforce_mcp.py une fonction de suppression:")
print("""
@mcp.tool(name="salesforce_delete_record")
async def salesforce_delete_record(sobject: str, record_id: str) -> Dict[str, Any]:
    \"\"\"
    Supprime un enregistrement Salesforce
    \"\"\"
    try:
        sf_client = get_salesforce_client()
        
        # Effectuer la suppression
        result = getattr(sf_client, sobject).delete(record_id)
        
        return {
            "success": True,
            "message": f"Enregistrement {record_id} supprimé avec succès"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Erreur lors de la suppression: {str(e)}"
        }
""")
print("\n✅ L'interface sera accessible à : http://localhost:8200/quote-management")
print("\n⚠️ Note: Assurez-vous que les services MCP SAP et Salesforce sont actifs")