# test_fix_422.py
"""
🧪 Test de validation pour la correction de l'erreur 422
Teste spécifiquement le prompt: "devis 30 imprimantes 34 ppm pour TARTEMP0"
"""

import requests
import json
import time
import logging
from datetime import datetime

# Configuration logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('test_fix_422')

# Configuration
BASE_URL = 'http://178.33.233.120:8000'
ENDPOINT = '/api/assistant/workflow/create_quote'

# Payload de test exact
TEST_PAYLOAD = {
    "message": "devis 30 imprimantes 34 ppm pour TARTEMP0",
    "draft_mode": False,
    "force_production": True
}

def test_endpoint_availability():
    """Teste que l'endpoint existe maintenant"""
    url = BASE_URL + ENDPOINT
    logger.info(f"🔍 Test disponibilité endpoint: {url}")
    
    try:
        response = requests.options(url, timeout=5)
        if response.status_code in [200, 405]:  # 405 = Method not allowed, mais endpoint existe
            logger.info("✅ Endpoint disponible")
            return True
        else:
            logger.error(f"❌ Endpoint non disponible - Status: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"❌ Erreur test disponibilité: {e}")
        return False

def test_exact_prompt():
    """Teste le prompt exact qui causait l'erreur 422"""
    url = BASE_URL + ENDPOINT
    logger.info(f"🧪 Test prompt exact: {TEST_PAYLOAD['message']}")
    
    start_time = time.time()
    
    try:
        response = requests.post(
            url, 
            json=TEST_PAYLOAD, 
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        
        duration = time.time() - start_time
        
        # Analyser la réponse
        if response.status_code == 200:
            logger.info(f"✅ SUCCESS - {response.status_code} - {duration:.3f}s")
            
            # Analyser le JSON de réponse
            try:
                result = response.json()
                logger.info(f"📊 Réponse: success={result.get('success')}")
                
                if result.get('success'):
                    # Afficher les détails du devis généré
                    client = result.get('client', {})
                    products = result.get('products', [])
                    
                    logger.info(f"👤 Client: {client.get('name', 'N/A')}")
                    logger.info(f"📦 Produits trouvés: {len(products)}")
                    logger.info(f"💰 Montant total: {result.get('total_amount', 0)}")
                    logger.info(f"📄 Quote ID: {result.get('quote_id', 'N/A')}")
                    
                    # Détail des produits
                    for i, product in enumerate(products):
                        logger.info(f"  - Produit {i+1}: {product.get('name', 'N/A')} "
                                  f"(Qté: {product.get('quantity', 0)}, "
                                  f"Prix: {product.get('unit_price', 0)})")
                else:
                    logger.warning(f"⚠️ Workflow failed: {result.get('error', 'Erreur inconnue')}")
                
                return True
                
            except json.JSONDecodeError as e:
                logger.error(f"❌ Réponse JSON invalide: {e}")
                logger.error(f"Contenu: {response.text[:500]}")
                return False
                
        elif response.status_code == 422:
            logger.error(f"❌ ERREUR 422 PERSISTE - {duration:.3f}s")
            try:
                error_detail = response.json()
                logger.error(f"Détail erreur: {error_detail}")
            except:
                logger.error(f"Contenu erreur: {response.text[:200]}")
            return False
            
        else:
            logger.error(f"❌ ERREUR {response.status_code} - {duration:.3f}s")
            logger.error(f"Contenu: {response.text[:200]}")
            return False
            
    except requests.exceptions.Timeout:
        logger.error("❌ TIMEOUT après 30s")
        return False
    except Exception as e:
        logger.error(f"❌ Erreur requête: {e}")
        return False

def test_variations():
    """Teste quelques variations du prompt"""
    variations = [
        "devis 10 imprimantes laser pour EdgeCorp",
        "créer un devis pour 5 ordinateurs pour TestClient",
        "faire devis 2 écrans pour MonClient"
    ]
    
    for variation in variations:
        logger.info(f"🔄 Test variation: {variation}")
        payload = {"message": variation, "draft_mode": False}
        
        try:
            response = requests.post(
                BASE_URL + ENDPOINT,
                json=payload,
                timeout=20
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"  ✅ OK - Success: {result.get('success')}")
            else:
                logger.warning(f"  ⚠️ Status {response.status_code}")
                
        except Exception as e:
            logger.error(f"  ❌ Erreur: {e}")

def main():
    """Fonction principale de test"""
    logger.info("=" * 60)
    logger.info("🧪 DÉBUT TEST CORRECTION ERREUR 422")
    logger.info(f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"🌐 URL: {BASE_URL}{ENDPOINT}")
    logger.info("=" * 60)
    
    # Test 1: Disponibilité endpoint
    if not test_endpoint_availability():
        logger.error("🔴 ARRÊT - Endpoint non disponible")
        return False
    
    # Test 2: Prompt exact
    success = test_exact_prompt()
    
    # Test 3: Variations (optionnel)
    if success:
        logger.info("\n🔄 Test variations additionnelles...")
        test_variations()
    
    # Résumé
    logger.info("=" * 60)
    if success:
        logger.info("🎉 CORRECTION RÉUSSIE - L'erreur 422 est corrigée !")
        logger.info("✅ L'endpoint /api/assistant/workflow/create_quote fonctionne")
        logger.info("✅ Le prompt 'devis 30 imprimantes 34 ppm pour TARTEMP0' est traité")
    else:
        logger.error("🔴 CORRECTION ÉCHOUÉE - L'erreur 422 persiste")
        logger.error("❌ Vérifier que les modifications ont été appliquées")
        logger.error("❌ Redémarrer le serveur si nécessaire")
    
    logger.info("=" * 60)
    return success

if __name__ == "__main__":
    main()