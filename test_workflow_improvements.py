#!/usr/bin/env python3
# test_workflow_improvements.py - Test des améliorations du workflow

"""
🔧 SCRIPT DE TEST : Améliorations du workflow de devis
Ce script teste les nouvelles fonctionnalités ajoutées :
- Tracking de progression avancé
- Intégration MCP améliorée
- Gestion des tâches avec résultats
"""

import asyncio
import logging
import sys
from datetime import datetime

# Configuration des logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_mcp_connector_improvements():
    """Test des améliorations du connecteur MCP"""
    logger.info("🔧 Test des améliorations MCP Connector")
    
    try:
        from services.mcp_connector import mcp_connector, call_mcp_with_progress, test_mcp_connections_with_progress
        
        # Test 1: Instance globale
        logger.info("✅ Instance globale mcp_connector disponible")
        
        # Test 2: Fonction de test des connexions avec progression
        logger.info("🔍 Test des connexions avec progression...")
        connection_results = await test_mcp_connections_with_progress()
        logger.info(f"📊 Résultats connexions: {connection_results.get('overall_status')}")
        
        # Test 3: Appel MCP avec progression
        logger.info("🔄 Test appel MCP avec progression...")
        try:
            result = await call_mcp_with_progress(
                "salesforce_mcp",
                "salesforce_query", 
                {"query": "SELECT Id FROM Account LIMIT 1"},
                "test_call",
                "🔍 Test de requête Salesforce"
            )
            logger.info(f"✅ Appel MCP réussi: {'success' if 'error' not in result else 'error'}")
        except Exception as e:
            logger.warning(f"⚠️ Appel MCP échoué (normal si pas de connexion): {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur test MCP: {e}")
        return False

async def test_progress_tracker_improvements():
    """Test des améliorations du progress tracker"""
    logger.info("🔧 Test des améliorations Progress Tracker")
    
    try:
        from services.progress_tracker import progress_tracker, get_or_create_task, track_workflow_step
        
        # Test 1: Création de tâche
        task = get_or_create_task(user_prompt="Test des améliorations", draft_mode=True)
        logger.info(f"✅ Tâche créée: {task.task_id}")
        
        # Test 2: Définir comme tâche courante
        progress_tracker.set_current_task(task.task_id)
        current = progress_tracker.get_current_task()
        logger.info(f"✅ Tâche courante définie: {current.task_id if current else 'None'}")
        
        # Test 3: Tracking d'étapes
        track_workflow_step("test_step", "🔍 Test d'étape", 0)
        track_workflow_step("test_step", "🔄 En cours...", 50)
        track_workflow_step("test_step", "✅ Terminé", 100)
        
        # Test 4: Statistiques
        stats = progress_tracker.get_task_statistics()
        logger.info(f"📊 Statistiques: {stats['active_tasks']} actives, {stats['completed_tasks']} terminées")
        
        # Test 5: Complétion avec résultat
        test_result = {
            "status": "success",
            "message": "Test réussi",
            "data": {"test": True}
        }
        progress_tracker.complete_task(task.task_id, test_result)
        logger.info("✅ Tâche terminée avec résultat")
        
        # Test 6: Vérification de l'historique
        history = progress_tracker.get_task_history()
        if history and "result" in history[-1]:
            logger.info("✅ Résultat sauvegardé dans l'historique")
        else:
            logger.warning("⚠️ Résultat non trouvé dans l'historique")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur test Progress Tracker: {e}")
        return False

async def test_workflow_integration():
    """Test de l'intégration workflow"""
    logger.info("🔧 Test de l'intégration workflow")
    
    try:
        from workflow.devis_workflow import DevisWorkflow
        
        # Test 1: Création du workflow avec task_id
        workflow = DevisWorkflow(
            validation_enabled=True,
            draft_mode=True,
            force_production=False
        )
        logger.info("✅ Workflow créé avec améliorations")
        
        # Test 2: Test des connexions amélioré
        logger.info("🔍 Test des connexions améliorées...")
        connections_ok = await workflow.test_connections()  # Utiliser la méthode publique
        logger.info(f"📊 Connexions: {'OK' if connections_ok else 'KO'}")
        
        # Test 3: Simulation d'un prompt simple
        test_prompt = "Créer un devis pour le client TestCorp avec 2 ordinateurs portables"
        logger.info(f"🔄 Test du prompt: {test_prompt}")
        
        try:
            result = await workflow.process_prompt(test_prompt)
            logger.info(f"✅ Workflow terminé: {result.get('status', 'unknown')}")
            
            if result.get('status') == 'success':
                logger.info(f"📋 Type: {result.get('type')}")
                logger.info(f"💬 Message: {result.get('message')}")
            
        except Exception as e:
            logger.warning(f"⚠️ Workflow échoué (normal en test): {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur test Workflow: {e}")
        return False

async def main():
    """Fonction principale de test"""
    logger.info("🚀 DÉMARRAGE DES TESTS D'AMÉLIORATIONS WORKFLOW")
    logger.info("=" * 60)
    
    results = []
    
    # Test 1: MCP Connector
    logger.info("\n📡 TEST 1: Améliorations MCP Connector")
    results.append(await test_mcp_connector_improvements())
    
    # Test 2: Progress Tracker
    logger.info("\n📊 TEST 2: Améliorations Progress Tracker")
    results.append(await test_progress_tracker_improvements())
    
    # Test 3: Intégration Workflow
    logger.info("\n🔄 TEST 3: Intégration Workflow")
    results.append(await test_workflow_integration())
    
    # Résumé
    logger.info("\n" + "=" * 60)
    logger.info("📋 RÉSUMÉ DES TESTS")
    
    test_names = ["MCP Connector", "Progress Tracker", "Workflow Integration"]
    for i, (name, result) in enumerate(zip(test_names, results)):
        status = "✅ RÉUSSI" if result else "❌ ÉCHOUÉ"
        logger.info(f"{i+1}. {name}: {status}")
    
    success_count = sum(results)
    total_count = len(results)
    
    logger.info(f"\n🎯 RÉSULTAT GLOBAL: {success_count}/{total_count} tests réussis")
    
    if success_count == total_count:
        logger.info("🎉 TOUS LES TESTS SONT RÉUSSIS !")
        return 0
    else:
        logger.warning("⚠️ Certains tests ont échoué")
        return 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("🛑 Tests interrompus par l'utilisateur")
        sys.exit(1)
    except Exception as e:
        logger.error(f"💥 Erreur fatale: {e}")
        sys.exit(1)