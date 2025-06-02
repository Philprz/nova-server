#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test de validation SIRET avec des entreprises réelles existantes
"""

import sys
import os
import asyncio
import logging
from datetime import datetime

# Ajouter le répertoire racine au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# SIRET d'entreprises réelles pour les tests
TEST_SIRET_CASES = [
    {
        "siret": "35600000000021",  # BPIFRANCE (connu dans la base INSEE)
        "description": "BPIFRANCE - Établissement principal"
    },
    {
        "siret": "13002526500013",  # SNCF VOYAGEURS (exemple connu)
        "description": "SNCF VOYAGEURS"
    },
    {
        "siret": "78925320700014",  # LA POSTE (exemple connu)
        "description": "LA POSTE"
    },
    {
        "siret": "32012345600000",  # SIRET invalide pour test d'erreur
        "description": "SIRET invalide (test d'erreur)"
    }
]

async def test_real_siret_validation():
    """Test de validation avec des SIRET réels"""
    logger.info("🧪 TEST DE VALIDATION SIRET AVEC ENTREPRISES RÉELLES")
    logger.info(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        from services.client_validator import ClientValidator
        logger.info("✅ ClientValidator importé avec succès")
    except ImportError as e:
        logger.error(f"❌ Erreur import ClientValidator: {e}")
        return
    
    validator = ClientValidator()
    
    for i, test_case in enumerate(TEST_SIRET_CASES, 1):
        logger.info(f"\n{'='*60}")
        logger.info(f"🧪 TEST {i}/{len(TEST_SIRET_CASES)}: {test_case['description']}")
        logger.info(f"SIRET: {test_case['siret']}")
        logger.info(f"{'='*60}")
        
        try:
            # Test de validation SIRET
            result = await validator._validate_siret_insee(test_case['siret'])
            
            logger.info("\n📊 RÉSULTAT:")
            logger.info(f"   Valide: {'✅ OUI' if result['valid'] else '❌ NON'}")
            
            if result['valid']:
                data = result.get('data', {})
                logger.info("   📋 DONNÉES RÉCUPÉRÉES:")
                logger.info(f"      Dénomination: {data.get('denomination', 'N/A')}")
                logger.info(f"      Activité principale: {data.get('activite_principale', 'N/A')}")
                logger.info(f"      Adresse: {data.get('adresse_complete', 'N/A')}")
                logger.info(f"      Code postal: {data.get('code_postal', 'N/A')}")
                logger.info(f"      Commune: {data.get('libelle_commune', 'N/A')}")
                logger.info(f"      État administratif: {data.get('etat_administratif', 'N/A')}")
                
                if data.get('date_creation'):
                    logger.info(f"      Date de création: {data['date_creation']}")
                
                logger.info(f"   🔧 Méthode: {result.get('validation_method', 'N/A')}")
            else:
                logger.warning(f"   ❌ Erreur: {result.get('error', 'Erreur inconnue')}")
                
                # Si c'est une erreur HTTP, afficher plus de détails
                if 'HTTP' in result.get('error', ''):
                    logger.warning("   💡 Suggestion: Ce SIRET peut ne pas exister dans la base INSEE")
            
        except Exception as e:
            logger.exception(f"💥 Exception lors du test {i}: {str(e)}")
        
        # Pause entre les tests
        if i < len(TEST_SIRET_CASES):
            logger.info("\n⏳ Pause de 2 secondes...")
            await asyncio.sleep(2)
    
    # Test avec données client complètes
    logger.info(f"\n{'='*80}")
    logger.info("🧪 TEST CLIENT COMPLET AVEC SIRET VALIDE")
    logger.info(f"{'='*80}")
    
    # Utiliser le premier SIRET qui devrait être valide
    test_client_data = {
        "company_name": "Test Entreprise SIRET",
        "siret": TEST_SIRET_CASES[0]["siret"],  # BPIFRANCE
        "email": "contact@test-entreprise.fr",
        "phone": "+33 1 23 45 67 89",
        "billing_street": "123 Rue Test",
        "billing_city": "Paris",
        "billing_postal_code": "75001",
        "billing_country": "France"
    }
    
    try:
        logger.info("Validation client complète avec SIRET réel...")
        result = await validator.validate_complete(test_client_data, "FR")
        
        logger.info("\n📊 RÉSULTAT VALIDATION COMPLÈTE:")
        logger.info(f"   Client valide: {'✅ OUI' if result['valid'] else '❌ NON'}")
        logger.info(f"   Erreurs: {len(result['errors'])}")
        logger.info(f"   Avertissements: {len(result['warnings'])}")
        logger.info(f"   Suggestions: {len(result['suggestions'])}")
        
        if result['errors']:
            logger.warning("   ❌ ERREURS:")
            for error in result['errors']:
                logger.warning(f"      - {error}")
        
        if result.get('enriched_data', {}).get('siret_data'):
            siret_data = result['enriched_data']['siret_data']
            logger.info("   ✨ DONNÉES SIRET ENRICHIES:")
            logger.info(f"      Entreprise: {siret_data.get('denomination', 'N/A')}")
            logger.info(f"      Activité: {siret_data.get('activite_principale', 'N/A')}")
            logger.info(f"      Adresse: {siret_data.get('adresse_complete', 'N/A')}")
        
    except Exception as e:
        logger.exception(f"💥 Exception lors du test client complet: {str(e)}")
    
    # Statistiques finales
    logger.info(f"\n{'='*80}")
    logger.info("📈 STATISTIQUES FINALES")
    logger.info(f"{'='*80}")
    
    stats = validator.get_stats()
    logger.info(f"Validations totales: {stats['validation_stats']['total_validations']}")
    logger.info(f"Validations réussies: {stats['validation_stats']['successful_validations']}")
    logger.info(f"Validations échouées: {stats['validation_stats']['failed_validations']}")
    logger.info(f"Taille du cache: {stats['cache_size']}")
    
    logger.info("\n🎯 CONCLUSION:")
    logger.info("Si au moins un SIRET a été validé avec succès, l'intégration API INSEE fonctionne.")
    logger.info("Les erreurs 404 sont normales pour les SIRET inexistants.")
    logger.info("L'important est que l'API réponde et traite les requêtes correctement.")

if __name__ == "__main__":
    asyncio.run(test_real_siret_validation())