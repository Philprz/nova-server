# Test pour diagnostiquer le problème d'affichage du nom client
# À exécuter depuis le répertoire NOVA-SERVER

import asyncio
import sys
import os
import json
import logging

# Configuration logging pour debug
logging.basicConfig(level=logging.DEBUG)

# Ajouter le répertoire racine au path
sys.path.insert(0, os.path.abspath('.'))

async def test_client_data_structure():
    """Test pour analyser la structure des données client retournées"""
    
    try:
        from workflow.devis_workflow import DevisWorkflow
        
        print("🔍 Test de diagnostic - Structure données client")
        print("=" * 50)
        
        # Test avec un devis simple
        prompt = "Faire un devis pour 500 unités A00002 pour le client SAFRAN"
        
        workflow = DevisWorkflow()
        result = await workflow.process_prompt(prompt, draft_mode=False)
        
        print("📊 STRUCTURE COMPLÈTE DE LA RÉPONSE :")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        print("\n" + "="*50)
        print("🎯 DONNÉES CLIENT SPÉCIFIQUES :")
        
        # Analyser la structure client
        client_data = result.get("client", {})
        print(f"Type client_data: {type(client_data)}")
        print(f"Contenu client: {client_data}")
        
        if isinstance(client_data, dict):
            print("\n🔍 Clés disponibles dans client:")
            for key, value in client_data.items():
                print(f"  • {key}: {value} (type: {type(value)})")
        
        print("\n" + "="*50)
        print("🏭 FORMATAGE POUR L'API :")
        
        # Simuler le formatage de routes_devis.py
        formatted_client = {
            "name": client_data.get("name", "Client extrait"),
            "account_number": client_data.get("account_number", "N/A"),
            "salesforce_id": client_data.get("salesforce_id", "")
        }
        
        print(f"Client formaté pour interface: {formatted_client}")
        
        print("\n" + "="*50)
        print("✅ DIAGNOSTIC TERMINÉ")
        
    except Exception as e:
        print(f"❌ Erreur lors du diagnostic: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_client_data_structure())