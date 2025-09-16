# scripts/migrate_to_local_search.py
# Migration progressive vers recherche locale avec tests

import os
import sys
import asyncio
import logging
from datetime import datetime
from pathlib import Path

# Ajout du répertoire parent au path
sys.path.append(str(Path(__file__).parent.parent))

from scripts.sync_sap_products import SAPProductSyncer
from services.local_product_search import LocalProductSearchService
from workflow.devis_workflow DevisWorkflow

logger = logging.getLogger('migration')

class ProgressiveMigration:
    """Migration progressive vers recherche locale sans interruption"""
    
    def __init__(self):
        self.syncer = SAPProductSyncer()
        self.local_service = LocalProductSearchService()
    
    async def run_migration(self):
        """Exécution migration complète"""
        
        logger.info("🚀 DÉBUT MIGRATION VERS RECHERCHE LOCALE")
        
        try:
            # ÉTAPE 1: Synchronisation initiale des produits
            logger.info("📥 ÉTAPE 1: Synchronisation produits SAP")
            sync_result = await self.syncer.run_full_sync()
            
            if not sync_result["success"]:
                raise Exception(f"Synchronisation échouée: {sync_result['error']}")
            
            logger.info(f"✅ {sync_result['products_synced']} produits synchronisés")
            
            # ÉTAPE 2: Tests de validation
            logger.info("🧪 ÉTAPE 2: Tests de validation")
            validation_success = await self._run_validation_tests()
            
            if not validation_success:
                raise Exception("Tests de validation échoués")
            
            # ÉTAPE 3: Configuration de synchronisation automatique  
            logger.info("⏰ ÉTAPE 3: Configuration synchronisation automatique")
            await self._setup_automatic_sync()
            
            logger.info("🎉 MIGRATION TERMINÉE AVEC SUCCÈS")
            return {"success": True, "message": "Migration vers recherche locale terminée"}
            
        except Exception as e:
            logger.error(f"❌ ÉCHEC MIGRATION: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def _run_validation_tests(self) -> bool:
        """Tests de validation post-migration"""
        
        test_products = [
            ("A00025", ""),  # Code exact
            ("imprimante laser", ""),  # Recherche par nom  
            ("HP LaserJet", "")  # Recherche marque
        ]
        
        success_count = 0
        
        for product_name, product_code in test_products:
            try:
                logger.info(f"🧪 Test recherche: {product_name}")
                
                # Test recherche locale
                local_result = await self.local_service.search_products(product_name, product_code)
                
                if local_result["found"]:
                    success_count += 1
                    logger.info(f"✅ Test réussi: {len(local_result['products'])} produits trouvés")
                else:
                    logger.warning(f"⚠️ Test échoué: aucun produit trouvé")
                    
            except Exception as e:
                logger.error(f"❌ Erreur test {product_name}: {str(e)}")
        
        success_rate = success_count / len(test_products)
        logger.info(f"📊 Taux de succès tests: {success_rate:.1%}")
        
        return success_rate >= 0.8  # Minimum 80% de succès
    
    async def _setup_automatic_sync(self):
        """Configuration synchronisation automatique quotidienne"""
        
        # Création du script de tâche planifiée Windows
        script_content = f"""
@echo off
cd /d "{os.getcwd()}"
call venv\\Scripts\\activate.bat
python scripts\\sync_sap_products.py
echo %date% %time% - Synchronisation produits terminée >> logs\\sync_schedule.log
"""
        
        with open("scripts/daily_sync.bat", "w", encoding="utf-8") as f:
            f.write(script_content)
        
        logger.info("📝 Script synchronisation quotidienne créé: scripts/daily_sync.bat")
        logger.info("⏰ Configurez dans le Planificateur de tâches Windows:")
        logger.info("   - Nom: NOVA Product Sync")  
        logger.info("   - Fréquence: Quotidienne à 02:00")
        logger.info("   - Action: scripts/daily_sync.bat")

if __name__ == "__main__":
    migration = ProgressiveMigration()
    result = asyncio.run(migration.run_migration())
    print(f"Résultat migration: {result}")