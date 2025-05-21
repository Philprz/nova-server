# tests/test_integration_complete.py
import os
import sys
import asyncio
import logging
from datetime import datetime
from workflow.devis_workflow import DevisWorkflow

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"logs/test_integration_{datetime.now().strftime('%Y%m%d%H%M%S')}.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("test_integration")

async def test_integration_complete(prompt=None):
    """
    Teste l'intégration complète entre Claude, Salesforce et SAP
    """
    if prompt is None:
        prompt = "faire un devis pour 50 ref A00001 pour le client Edge Communications"
    
    logger.info(f"Test d'intégration complète avec la demande: {prompt}")
    
    workflow = DevisWorkflow()
    
    try:
        # Exécuter le workflow
        result = await workflow.process_prompt(prompt)
        
        # Vérifier le résultat
        logger.info(f"Résultat du workflow: {result}")
        
        # Vérifier l'intégration Salesforce
        if result.get("status") == "success" and result.get("quote_id"):
            logger.info(f"✅ Intégration Salesforce réussie: Devis {result.get('quote_id')} créé")
        else:
            logger.error(f"❌ Intégration Salesforce échouée: {result.get('message')}")
        
        # Vérifier l'intégration SAP
        if result.get("sap_reference"):
            logger.info(f"✅ Intégration SAP réussie: Document SAP {result.get('sap_reference')} créé")
        else:
            logger.error(f"❌ Intégration SAP échouée: Pas de référence SAP dans le résultat")
        
        return result
    except Exception as e:
        logger.exception(f"Erreur lors du test d'intégration: {str(e)}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    asyncio.run(test_integration_complete())