# test_nova_fix.py
"""
Test de validation pour la correction 422
"""

import requests
import json
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('test_422')

BASE_URL = 'http://178.33.233.120:8000'

def test_fix():
    """Test le prompt exact qui causait l'erreur"""
    url = f"{BASE_URL}/api/assistant/workflow/create_quote"
    
    payload = {
        "message": "devis 30 imprimantes 34 ppm pour TARTEMP0",
        "draft_mode": False,
        "force_production": True
    }
    
    logger.info(f"🧪 Test: {payload['message']}")
    
    try:
        response = requests.post(
            url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        
        logger.info(f"📊 Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            logger.info("✅ SUCCÈS - Erreur 422 corrigée!")
            logger.info(f"📋 Réponse: {json.dumps(result, indent=2)}")
            return True
        elif response.status_code == 422:
            logger.error("❌ ÉCHEC - Erreur 422 persiste")
            logger.error(f"📋 Détails: {response.json()}")
            return False
        else:
            logger.warning(f"⚠️ Status inattendu: {response.status_code}")
            logger.warning(f"📋 Réponse: {response.text[:200]}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Erreur: {e}")
        return False

if __name__ == "__main__":
    logger.info("="*60)
    logger.info(f"🚀 TEST CORRECTION 422 - {datetime.now()}")
    logger.info("="*60)
    
    success = test_fix()
    
    if success:
        logger.info("\n🎉 Correction validée - Le système fonctionne!")
    else:
        logger.error("\n🔴 La correction doit être appliquée au serveur")
        logger.info("\n📝 Actions requises:")
        logger.info("1. Appliquer fix_422_endpoint.py dans routes/routes_intelligent_assistant.py")
        logger.info("2. Redémarrer le serveur: uvicorn main:app --reload --host 0.0.0.0 --port 8000")
        logger.info("3. Relancer ce test")