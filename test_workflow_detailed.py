# test_workflow_detailed.py
import asyncio
import json
import logging
from datetime import datetime
from workflow.devis_workflow import DevisWorkflow

# Configuration du logging pour voir tout
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'test_detailed_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

async def test_workflow_step_by_step():
    """Test détaillé étape par étape"""
    print("=== TEST DÉTAILLÉ DU WORKFLOW ===")
    
    workflow = DevisWorkflow()
    prompt = "faire un devis pour 500 ref A00002 pour le client Edge Communications"
    
    print(f"Prompt: {prompt}")
    print()
    
    try:
        # Lancer le workflow avec logging détaillé
        result = await workflow.process_prompt(prompt)
        
        # Enregistrer le résultat
        filename = f"test_result_detailed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False, default=str)
        
        print("=== RÉSULTAT WORKFLOW ===")
        print(f"Statut: {result.get('status')}")
        print(f"Message: {result.get('message')}")
        
        if result.get('status') == 'success':
            print(f"✅ Quote ID: {result.get('quote_id')}")
            print(f"✅ SAP DocNum: {result.get('sap_doc_num')}")
            print(f"✅ SAP DocEntry: {result.get('sap_doc_entry')}")
            print(f"✅ Client: {result.get('client', {}).get('name')}")
            print(f"✅ Montant: {result.get('total_amount')} {result.get('currency')}")
        else:
            print(f"❌ Erreur: {result.get('message')}")
            if result.get('error_details'):
                print(f"❌ Détails: {result.get('error_details')}")
        
        print(f"\nRésultat complet sauvé dans: {filename}")
        
        return result
        
    except Exception as e:
        print(f"❌ Exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    result = asyncio.run(test_workflow_step_by_step())