# c:\Users\PPZ\NOVA-SERVER\test
import asyncio
import logging
from services.mcp_connector import get_mcp_connector, MCPConnector
from services.llm_extractor import get_llm_extractor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("test_corrections_complete")

async def test_all_corrections_with_data():
    """Test complet avec vérification de récupération de vraies données"""
    
    print("🚀 === DÉMARRAGE DES TESTS COMPLETS ===\n")
    
    # Test 1: Instance LLMExtractor
    print("=== Test 1: LLMExtractor ===")
    try:
        extractor = get_llm_extractor()
        logger.info("✅ LLMExtractor instance créée")
        
        # Test méthode extract_quote_request
        test_text = "Je voudrais un devis pour 3 imprimantes HP LaserJet Pro pour la société TestCorp"
        result = await extractor.extract_quote_request(test_text)
        logger.info(f"✅ extract_quote_request fonctionne: {result['success']}")
        
        # Test extraction de données client
        client_result = await extractor.extract_customer_data(test_text)
        logger.info(f"✅ extract_customer_data fonctionne: {client_result['success']}")
        
    except Exception as e:
        logger.error(f"❌ Erreur LLMExtractor: {e}")
    
    print("\n" + "="*50 + "\n")
    
    # Test 2: MCPConnector - Connexions
    print("=== Test 2: MCPConnector - Connexions ===")
    try:
        connector = get_mcp_connector()
        
        # Test connexions
        sap_login = await connector.sap_login()
        logger.info(f"✅ sap_login: {sap_login['success']}")
        
        sf_login = await connector.salesforce_login()
        logger.info(f"✅ salesforce_login: {sf_login['success']}")
        
        # Test nouvelles méthodes
        claude_test = await connector.claude_api_test()
        logger.info(f"✅ claude_api_test: {claude_test['success']}")
        
        routes = connector.routes_availability()
        logger.info(f"✅ routes_availability: {routes['active_routes']}/{routes['total_routes']}")
        
    except Exception as e:
        logger.error(f"❌ Erreur MCPConnector connexions: {e}")
    
    print("\n" + "="*50 + "\n")
    
    # Test 3: NOUVELLES VÉRIFICATIONS - Récupération de vraies données
    print("=== Test 3: Récupération de VRAIES DONNÉES ===")
    
    # Test Salesforce - Récupération de comptes réels
    print("\n--- Test Salesforce Data ---")
    try:
        # Via méthodes statiques MCP
        sf_accounts = await MCPConnector.get_salesforce_accounts(limit=5)
        if "error" not in sf_accounts:
            records = sf_accounts.get("records", [])
            logger.info(f"✅ Salesforce: {len(records)} comptes récupérés")
            if records:
                logger.info(f"   Premier compte: {records[0].get('Name', 'N/A')}")
        else:
            logger.error(f"❌ Erreur Salesforce: {sf_accounts['error']}")
        
        # Test query SOQL personnalisée
        custom_query = "SELECT Id, Name, CreatedDate FROM Account LIMIT 3"
        query_result = await MCPConnector.salesforce_query(custom_query)
        if "error" not in query_result:
            query_records = query_result.get("records", [])
            logger.info(f"✅ Query SOQL: {len(query_records)} résultats")
        else:
            logger.error(f"❌ Erreur Query SOQL: {query_result['error']}")
        
    except Exception as e:
        logger.error(f"❌ Erreur récupération Salesforce: {e}")
    
    # Test SAP - Récupération de produits réels
    print("\n--- Test SAP Data ---")
    try:
        # Via méthodes statiques MCP
        sap_products = await MCPConnector.get_sap_products(limit=5)
        if "products" in sap_products and sap_products["success"]:
            products = sap_products["products"]
            logger.info(f"✅ SAP: {len(products)} produits récupérés")
            if products:
                logger.info(f"   Premier produit: {products[0].get('ItemName', 'N/A')} ({products[0].get('ItemCode', 'N/A')})")
        else:
            logger.error(f"❌ Erreur SAP products: {sap_products.get('error', 'Erreur inconnue')}")
        
        # Test recherche produit avec terme spécifique
        search_result = await MCPConnector.get_sap_products(search_term="HP", limit=3)
        if "products" in search_result and search_result["success"]:
            search_products = search_result["products"]
            logger.info(f"✅ SAP Search 'HP': {len(search_products)} produits trouvés")
        else:
            logger.error(f"❌ Erreur SAP search: {search_result.get('error', 'Erreur inconnue')}")
        
    except Exception as e:
        logger.error(f"❌ Erreur récupération SAP: {e}")
    
    print("\n" + "="*50 + "\n")
    
    # Test 4: Test d'intégration complet
    print("=== Test 4: Intégration LLM + Data ===")
    try:
        # Simulation d'une demande utilisateur complète
        user_request = "Je cherche des imprimantes laser couleur pour mon bureau"
        
        # 1. Extraction LLM
        extraction = await extractor.extract_quote_info(user_request)
        logger.info(f"✅ Extraction type: {extraction.get('action_type', 'Non détecté')}")
        
        # 2. Si c'est une recherche produit, on cherche dans SAP
        if extraction.get("action_type") == "RECHERCHE_PRODUIT":
            search_criteria = extraction.get("search_criteria", {})
            category = search_criteria.get("category", "imprimante")
            
            # Recherche dans SAP basée sur l'extraction
            if "imprimante" in category.lower() or "printer" in category.lower():
                printer_results = await MCPConnector.get_sap_products(search_term="printer", limit=3)
                if printer_results.get("success"):
                    logger.info(f"✅ Intégration réussie: {len(printer_results['products'])} imprimantes trouvées")
                else:
                    logger.warning("⚠️ Aucune imprimante trouvée dans SAP")
        
    except Exception as e:
        logger.error(f"❌ Erreur test intégration: {e}")
    
    print("\n🏁 === FIN DES TESTS ===")

async def test_data_verification_only():
    """Test focalisé uniquement sur la vérification des données"""
    
    print("🔍 === VÉRIFICATION DONNÉES UNIQUEMENT ===\n")
    
    try:
        # Test direct des données Salesforce
        print("--- Vérification Salesforce ---")
        sf_result = await MCPConnector.get_salesforce_accounts(limit=2)
        
        if "records" in sf_result:
            records = sf_result["records"]
            print(f"📊 Salesforce connecté: {len(records)} comptes")
            for i, record in enumerate(records[:2], 1):
                print(f"   {i}. {record.get('Name', 'Sans nom')} (ID: {record.get('Id', 'N/A')})")
        else:
            print(f"❌ Salesforce: {sf_result.get('error', 'Erreur inconnue')}")
        
        # Test direct des données SAP
        print("\n--- Vérification SAP ---")
        sap_result = await MCPConnector.get_sap_products(limit=2)
        
        if sap_result.get("success") and "products" in sap_result:
            products = sap_result["products"]
            print(f"📦 SAP connecté: {len(products)} produits")
            for i, product in enumerate(products[:2], 1):
                print(f"   {i}. {product.get('ItemName', 'Sans nom')} ({product.get('ItemCode', 'N/A')})")
        else:
            print(f"❌ SAP: {sap_result.get('error', 'Erreur inconnue')}")
        
    except Exception as e:
        print(f"❌ Erreur vérification données: {e}")

if __name__ == "__main__":
    print("Quel test voulez-vous exécuter ?")
    print("1. Tests complets (connexions + données)")
    print("2. Vérification données uniquement")
    
    choice = input("Choix (1 ou 2): ").strip()
    
    if choice == "2":
        asyncio.run(test_data_verification_only())
    else:
        asyncio.run(test_all_corrections_with_data())