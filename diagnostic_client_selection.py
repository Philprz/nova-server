#!/usr/bin/env python3
"""
Script de diagnostic pour tester la sélection de clients RONDOT
"""

import asyncio
import json
import logging
from utils.client_lister import find_client_everywhere
from workflow. import DevisWorkflow

# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_client_selection():
    """Test de la fonctionnalité de sélection des clients"""
    
    logger.info("🔍 === TEST SÉLECTION CLIENTS RONDOT ===")
    
    # 1. Test de recherche directe
    logger.info("1️⃣ Test de recherche client 'RONDOT'")
    try:
        search_result = await find_client_everywhere("RONDOT")
        total_found = search_result.get("total_found", 0)
        logger.info(f"✅ Clients trouvés: {total_found}")
        
        if total_found > 0:
            # Afficher les détails des clients trouvés
            for source in ['salesforce', 'sap']:
                clients = search_result.get(source, {}).get("clients", [])
                if clients:
                    logger.info(f"📊 {source.upper()}: {len(clients)} clients")
                    for i, client in enumerate(clients):
                        name = client.get('Name' if source == 'salesforce' else 'CardName', 'Nom non trouvé')
                        id_field = client.get('Id' if source == 'salesforce' else 'CardCode', 'ID non trouvé')
                        logger.info(f"  - Client {i+1}: {name} (ID: {id_field})")
        
    except Exception as e:
        logger.error(f"❌ Erreur recherche client: {e}")
        return False
    
    # 2. Test du workflow de sélection
    logger.info("2️⃣ Test du workflow de sélection")
    try:
        workflow = DevisWorkflow(task_id="test_diagnostic_client_selection")
        client_validation_result = await workflow._process_client_validation("RONDOT")
        
        logger.info(f"📊 Statut validation: {client_validation_result.get('status')}")
        logger.info(f"📊 Nécessite interaction: {client_validation_result.get('requires_user_selection', False)}")
        
        if client_validation_result.get("interaction_data"):
            interaction_data = client_validation_result["interaction_data"]
            client_options = interaction_data.get("client_options", [])
            logger.info(f"📊 Options disponibles dans interaction_data: {len(client_options)}")
            
            # Afficher chaque option
            for i, client in enumerate(client_options):
                logger.info(f"  ✨ Option {i+1}: {client.get('name')} ({client.get('source')}) - ID: {client.get('id')}")
                details = client.get('details', {})
                if details:
                    for key, value in details.items():
                        if value:
                            logger.info(f"     - {key}: {value}")
        
        # 3. Test de format WebSocket
        logger.info("3️⃣ Test du format de données WebSocket")
        
        if client_validation_result.get("status") == "user_interaction_required":
            # Simuler le format WebSocket
            websocket_data = {
                "type": "user_interaction_required",
                "task_id": "test_diagnostic_client_selection",
                "interaction_data": client_validation_result.get("interaction_data", client_validation_result)
            }
            
            logger.info("📨 Données WebSocket simulées:")
            logger.info(json.dumps(websocket_data, indent=2, default=str))
            
            # Vérifier la conformité
            interaction_data = websocket_data["interaction_data"]
            required_fields = ["client_options", "interaction_type", "original_client_name"]
            
            for field in required_fields:
                if field in interaction_data:
                    logger.info(f"✅ Champ {field}: présent")
                else:
                    logger.error(f"❌ Champ {field}: MANQUANT")
            
            # Test de la structure des client_options
            client_options = interaction_data.get("client_options", [])
            if client_options:
                sample_client = client_options[0]
                required_client_fields = ["id", "name", "source", "details"]
                
                logger.info("📊 Structure du premier client:")
                for field in required_client_fields:
                    if field in sample_client:
                        logger.info(f"✅ Champ client.{field}: présent")
                    else:
                        logger.error(f"❌ Champ client.{field}: MANQUANT")
            
            return True
        else:
            logger.warning(f"⚠️ Status inattendu: {client_validation_result.get('status')}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Erreur test workflow: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    asyncio.run(test_client_selection())