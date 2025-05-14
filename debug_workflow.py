import asyncio
from workflow.devis_workflow import DevisWorkflow

async def debug_workflow():
    workflow = DevisWorkflow()
    prompt = "faire un devis sur la fourniture de 500 ref A00001 pour le client Edge Communications"
    
    print("=== DÉBOGAGE DU WORKFLOW ===")
    result = await workflow.debug_test(prompt)
    
    print("\n=== RÉSULTAT D'EXTRACTION ===")
    print(result["extraction"])
    
    print("\n=== VALIDATION DU CLIENT ===")
    print(result["client_validation"])

if __name__ == "__main__":
    asyncio.run(debug_workflow())