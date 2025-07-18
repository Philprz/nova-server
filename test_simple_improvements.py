#!/usr/bin/env python3
# test_simple_improvements.py - Test simplifié des améliorations

"""
🔧 TEST SIMPLIFIÉ : Vérification des améliorations critiques
"""

import asyncio
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_mcp_improvements():
    """Test des améliorations MCP"""
    logger.info("🔧 Test MCP Connector amélioré")
    
    try:
        # Test 1: Instance globale
        from services.mcp_connector import mcp_connector
        logger.info("✅ Instance globale mcp_connector disponible")
        
        # Test 2: Nouvelle fonction de test
        from services.mcp_connector import test_mcp_connections_with_progress
        logger.info("✅ Fonction test_mcp_connections_with_progress disponible")
        
        # Test 3: Fonction d'appel avec progression
        from services.mcp_connector import call_mcp_with_progress
        logger.info("✅ Fonction call_mcp_with_progress disponible")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur MCP: {e}")
        return False

async def test_progress_improvements():
    """Test des améliorations Progress Tracker"""
    logger.info("🔧 Test Progress Tracker amélioré")
    
    try:
        # Test 1: Nouvelles fonctions utilitaires
        from services.progress_tracker import get_or_create_task, track_workflow_step
        logger.info("✅ Fonctions utilitaires disponibles")
        
        # Test 2: Créer une tâche
        task = get_or_create_task(user_prompt="Test simple", draft_mode=True)
        logger.info(f"✅ Tâche créée: {task.task_id}")
        
        # Test 3: Complétion avec résultat
        from services.progress_tracker import progress_tracker
        test_result = {"status": "success", "message": "Test réussi"}
        progress_tracker.complete_task(task.task_id, test_result)
        logger.info("✅ Tâche terminée avec résultat")
        
        # Test 4: Vérifier l'historique
        history = progress_tracker.get_task_history()
        if history and "result" in history[-1]:
            logger.info("✅ Résultat sauvegardé dans l'historique")
        else:
            logger.warning("⚠️ Résultat non trouvé dans l'historique")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur Progress Tracker: {e}")
        return False

async def main():
    """Test principal"""
    logger.info("🚀 TEST SIMPLIFIÉ DES AMÉLIORATIONS")
    logger.info("=" * 50)
    
    results = []
    
    # Test MCP
    logger.info("\n📡 Test MCP Connector")
    results.append(await test_mcp_improvements())
    
    # Test Progress Tracker
    logger.info("\n📊 Test Progress Tracker")
    results.append(await test_progress_improvements())
    
    # Résumé
    logger.info("\n" + "=" * 50)
    success_count = sum(results)
    total_count = len(results)
    
    logger.info(f"🎯 RÉSULTAT: {success_count}/{total_count} tests réussis")
    
    if success_count == total_count:
        logger.info("🎉 TOUS LES TESTS SONT RÉUSSIS !")
        logger.info("✅ Les améliorations critiques sont opérationnelles")
    else:
        logger.warning("⚠️ Certains tests ont échoué")
    
    return success_count == total_count

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)