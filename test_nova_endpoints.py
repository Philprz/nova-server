import requests
import time
import logging
from datetime import datetime

# Config logging pour matcher ton style de log (avec timestamps et INFO/ERROR)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('nova_endpoint_tester')

# URL de base (change si tu testes localement, ex: 'http://localhost:8000')
BASE_URL = 'http://178.33.233.120:8000'

# Endpoints à tester (basés sur ton repo et README)
ENDPOINTS = {
    'itspirit': '/interface/itspirit',  # GET pour vérifier l'interface
    'health': '/health',                # GET pour health check
    'create_quote': '/api/assistant/workflow/create_quote'  # POST pour créer un devis
}

# Payload exemple pour POST create_quote (basé sur tes tests comme "faire un devis pour Edge Communications")
# Ça évite le 422 : assure-toi que 'message' est un prompt valide en langage naturel
SAMPLE_PAYLOAD = {
    "message": "Créer un devis pour 100 unités de référence A00025 pour le client Edge Communications avec validation SIRET."
    # Ajoute d'autres champs si ton workflow en a besoin, ex: "client_id": "CD451796", "products": [{"ref": "A00025", "quantity": 100}]
}

def test_get_endpoint(endpoint, expected_status=200):
    """Teste un GET sur un endpoint et log le résultat."""
    url = BASE_URL + endpoint
    start_time = time.time()
    try:
        response = requests.get(url, timeout=5)
        duration = time.time() - start_time
        if response.status_code == expected_status:
            logger.info(f"✅ GET {url} - {response.status_code} - {duration:.3f}s")
            return True
        else:
            logger.error(f"❌ GET {url} - {response.status_code} - {duration:.3f}s - Contenu: {response.text[:200]}")
            return False
    except requests.RequestException as e:
        logger.error(f"❌ Erreur sur GET {url}: {str(e)}")
        return False

def test_post_create_quote(payload, expected_status=200):
    """Teste un POST sur create_quote avec payload pour simuler un 'order' depuis l'interface."""
    url = BASE_URL + ENDPOINTS['create_quote']
    headers = {'Content-Type': 'application/json'}
    start_time = time.time()
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        duration = time.time() - start_time
        if response.status_code == expected_status:
            logger.info(f"✅ POST {url} - {response.status_code} - {duration:.3f}s - Réponse: {response.json()}")
            return True
        elif response.status_code == 422:
            logger.warning(f"⚠️ POST {url} - 422 (Validation failed) - Vérifie le payload: {response.json()['detail']}")
            logger.info("💡 Fix possible: Assure-toi que 'message' est présent et valide. Exemple: Ajoute des champs comme client/products.")
        else:
            logger.error(f"❌ POST {url} - {response.status_code} - {duration:.3f}s - Contenu: {response.text[:200]}")
        return False
    except requests.RequestException as e:
        logger.error(f"❌ Erreur sur POST {url}: {str(e)}")
        return False

if __name__ == "__main__":
    logger.info(f"🛠️ Démarrage du test des endpoints NOVA - Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Test GET /interface/itspirit
    test_get_endpoint(ENDPOINTS['itspirit'])
    
    # Test GET /health
    test_get_endpoint(ENDPOINTS['health'])
    
    # Test POST /api/assistant/workflow/create_quote avec payload pour simuler l'ordre manquant
    test_post_create_quote(SAMPLE_PAYLOAD)
    
    logger.info("✅ Tests terminés. Si 422 persiste, check routes/routes_devis.py ou workflow/devis_workflow.py pour les validators Pydantic.")