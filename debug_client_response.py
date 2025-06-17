# debug_client_response.py
# Script pour diagnostiquer la structure exacte des données client

import asyncio
import json
import logging
import sys
import os

# Ajouter le répertoire racine au path
sys.path.insert(0, os.path.abspath('.'))

# Configuration logging
logging.basicConfig(level=logging.INFO)

async def test_client_data():
    """Test pour voir exactement ce que retourne le workflow"""
    
    try:
        from workflow.devis_workflow import DevisWorkflow
        
        print("🔍 DIAGNOSTIC - Structure données client SAFRAN")
        print("=" * 60)
        
        prompt = "Faire un devis pour 500 unités A00002 pour le client SAFRAN"
        
        workflow = DevisWorkflow()
        result = await workflow.process_prompt(prompt, draft_mode=False)
        
        print("📊 RÉSULTAT COMPLET DU WORKFLOW :")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        print("\n" + "="*60)
        print("🎯 ANALYSE SPÉCIFIQUE - DONNÉES CLIENT :")
        
        # Vérifier success
        print(f"✅ Succès: {result.get('success')}")
        print(f"✅ Status: {result.get('status')}")
        
        # Analyser les données client
        client_data = result.get("client")
        print(f"\n🏢 Type données client: {type(client_data)}")
        print(f"🏢 Contenu client: {client_data}")
        
        if isinstance(client_data, dict):
            print("\n📋 DÉTAIL DES CHAMPS CLIENT :")
            for key, value in client_data.items():
                print(f"  • {key}: '{value}' (type: {type(value)})")
                
            # Test spécifique name
            client_name = client_data.get("name")
            print(f"\n🎯 client.name = '{client_name}'")
            
        else:
            print(f"❌ PROBLÈME: client n'est pas un dict mais {type(client_data)}")
        
        print("\n" + "="*60)
        print("🧪 SIMULATION FORMATAGE ROUTE API :")
        
        # Simuler ce que fait routes_devis.py
        formatted_client_name = result.get("client", {}).get("name", "Client extrait")
        print(f"Route API récupérerait: '{formatted_client_name}'")
        
        if formatted_client_name == "Client extrait":
            print("❌ PROBLÈME IDENTIFIÉ: Route API utilise la valeur par défaut")
            print("Causes possibles:")
            print("  1. result.get('client') retourne None")
            print("  2. client n'a pas de clé 'name'")
            print("  3. client['name'] est None ou vide")
        else:
            print("✅ OK: Route API récupérerait le bon nom")
        
        print("\n" + "="*60)
        print("✅ DIAGNOSTIC TERMINÉ")
        
    except Exception as e:
        print(f"❌ Erreur: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_client_data())