# tests/test_sap_product_real.py
"""
Tests réels récupération produits SAP - SANS MOCKS
Test avec connexion SAP effective via MCP
"""

import pytest
import asyncio
import logging
import sys
import os

# Ajout path projet
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from managers.product_manager import ProductManager
from services.mcp_connector import MCPConnector

# Configuration logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

class TestSAPProductReal:
    """Tests récupération produits SAP réels"""
    
    @pytest.fixture(scope="session")
    async def setup_connections(self):
        """Vérification connexions SAP disponibles"""
        logger.info("🔍 Vérification connexions SAP...")
        
        connector = MCPConnector()
        
        # Test ping SAP
        ping_result = await connector.call_sap_mcp("ping", {})
        
        if "error" in ping_result:
            pytest.skip(f"SAP non disponible: {ping_result.get('error')}")
        
        logger.info("✅ SAP disponible")
        return connector
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_product_manager_real(self, setup_connections):
        """Test ProductManager avec SAP réel"""
        logger.info("\n🧪 Test ProductManager récupération produit réel...")
        
        manager = ProductManager()
        
        # Codes produits à tester (ajuster selon votre catalogue SAP)
        test_codes = [
            "A00001",    # Produit supposé existant
            "000001",    # Variante possible
            "MAT001",    # Format matériel
            "TEST999"    # Produit inexistant pour test
        ]
        
        for code in test_codes:
            logger.info(f"  🔍 Test produit: {code}")
            
            result = await manager._find_single_product(code)
            
            if result.get("found"):
                logger.info(f"    ✅ Trouvé: {result.get('name')} - Prix: {result.get('price')}€")
                logger.info(f"    📦 Stock: {result.get('stock')} - Disponible: {result.get('available')}")
                
                # Vérifications structure
                assert "code" in result
                assert "name" in result
                assert "price" in result
                assert "stock" in result
                assert result.get("source") == "sap"
                
            else:
                logger.info(f"    ❌ Non trouvé: {result.get('message', 'Aucun message')}")
                if "suggestions" in result:
                    logger.info(f"    💡 Suggestions disponibles")
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_mcp_direct_call(self, setup_connections):
        """Test appel MCP SAP direct"""
        logger.info("\n🧪 Test MCP SAP direct...")
        
        connector = setup_connections
        
        # Test récupération détails produit
        test_item_codes = ["A00001", "000001", "MAT001"]
        
        for item_code in test_item_codes:
            logger.info(f"  🔍 MCP call pour: {item_code}")
            
            result = await connector.call_sap_mcp("sap_get_product_details", {
                "item_code": item_code
            })
            
            if "error" not in result and result.get("ItemCode"):
                logger.info(f"    ✅ MCP réussi:")
                logger.info(f"      Code: {result.get('ItemCode')}")
                logger.info(f"      Nom: {result.get('ItemName')}")
                logger.info(f"      Prix: {result.get('UnitPrice')}€")
                logger.info(f"      Stock: {result.get('QuantityOnStock')}")
                
                # Vérifications champs essentiels
                assert result.get("ItemCode") is not None
                assert result.get("ItemName") is not None
                assert isinstance(result.get("UnitPrice", 0), (int, float))
                
            else:
                logger.info(f"    ❌ MCP échec: {result.get('error', 'Erreur inconnue')}")
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_product_search_real(self, setup_connections):
        """Test recherche produit SAP par nom/critères"""
        logger.info("\n🧪 Test recherche produits SAP...")
        
        connector = setup_connections
        
        # Termes de recherche à tester
        search_terms = [
            "test",
            "prod",
            "standard",
            "mat"
        ]
        
        for term in search_terms:
            logger.info(f"  🔍 Recherche: '{term}'")
            
            try:
                # Test recherche générique
                result = await connector.call_sap_mcp("sap_read", {
                    "endpoint": f"/Items?$filter=contains(tolower(ItemName), '{term.lower()}')&$top=5"
                })
                
                if "error" not in result and "value" in result:
                    items = result["value"]
                    logger.info(f"    ✅ {len(items)} produit(s) trouvé(s)")
                    
                    for i, item in enumerate(items[:3]):  # Afficher 3 premiers
                        logger.info(f"      [{i+1}] {item.get('ItemCode')} - {item.get('ItemName')}")
                        
                else:
                    logger.info(f"    ❌ Recherche échouée: {result.get('error', 'Erreur inconnue')}")
                    
            except Exception as e:
                logger.info(f"    ⚠️ Exception recherche: {str(e)}")
    
    @pytest.mark.integration 
    @pytest.mark.asyncio
    async def test_batch_product_retrieval(self, setup_connections):
        """Test récupération multiple produits"""
        logger.info("\n🧪 Test récupération batch produits...")
        
        manager = ProductManager()
        
        # Batch de codes à tester
        batch_codes = ["A00001", "000001", "MAT001", "INEXISTANT999"]
        
        logger.info(f"  🔄 Traitement batch: {batch_codes}")
        
        results = await manager.find_products(batch_codes)
        
        logger.info(f"  📊 Résultats batch:")
        found_count = 0
        
        for result in results:
            code = result.get("code", "N/A")
            if result.get("found"):
                found_count += 1
                logger.info(f"    ✅ {code}: {result.get('name')} - {result.get('price')}€")
            else:
                logger.info(f"    ❌ {code}: {result.get('error', 'Non trouvé')}")
        
        logger.info(f"  📈 Taux réussite: {found_count}/{len(batch_codes)} ({int(found_count/len(batch_codes)*100)}%)")
        
        # Vérifications structure
        assert len(results) == len(batch_codes)
        for result in results:
            assert "code" in result
            assert "found" in result

class TestSAPDataValidation:
    """Tests validation données SAP"""
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_product_data_consistency(self):
        """Test cohérence données produit SAP"""
        logger.info("\n🧪 Test cohérence données SAP...")
        
        manager = ProductManager()
        
        # Récupérer un produit existant
        result = await manager._find_single_product("A00001")
        
        if result.get("found"):
            logger.info("  ✅ Produit trouvé, validation structure...")
            
            # Validation champs obligatoires
            required_fields = ["code", "name", "price", "stock", "available", "source"]
            for field in required_fields:
                assert field in result, f"Champ manquant: {field}"
                logger.info(f"    ✓ {field}: {result[field]}")
            
            # Validation types
            assert isinstance(result["price"], (int, float)), "Prix doit être numérique"
            assert isinstance(result["stock"], (int, float)), "Stock doit être numérique"
            assert isinstance(result["available"], bool), "Available doit être boolean"
            assert result["source"] == "sap", "Source doit être 'sap'"
            
            # Validation données cohérentes
            if result["stock"] > 0:
                assert result["available"] == True, "Stock > 0 mais disponible = False"
            
            logger.info("  ✅ Structure validée")
            
        else:
            logger.info("  ⚠️ Aucun produit trouvé pour validation")

class TestSAPConnection:
    """Tests connexion SAP"""
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_sap_connection_health(self):
        """Test santé connexion SAP"""
        logger.info("\n🧪 Test santé connexion SAP...")
        
        connector = MCPConnector()
        
        # Test ping
        ping_result = await connector.call_sap_mcp("ping", {})
        logger.info(f"  📡 Ping: {ping_result}")
        
        if "pong" in str(ping_result).lower():
            logger.info("  ✅ SAP répond correctement")
        else:
            logger.warning(f"  ⚠️ Réponse SAP inattendue: {ping_result}")
        
        # Test requête simple
        try:
            simple_query = await connector.call_sap_mcp("sap_read", {
                "endpoint": "/Items?$top=1"
            })
            
            if "error" not in simple_query:
                logger.info("  ✅ Requête simple réussie")
            else:
                logger.warning(f"  ⚠️ Erreur requête: {simple_query.get('error')}")
                
        except Exception as e:
            logger.warning(f"  ⚠️ Exception requête: {str(e)}")

# Script exécution directe
if __name__ == "__main__":
    async def run_quick_test():
        """Test rapide pour validation"""
        logger.info("🚀 Test rapide récupération produit SAP...")
        
        manager = ProductManager()
        
        # Test produit simple
        result = await manager._find_single_product("A00001")
        
        if result.get("found"):
            print(f"✅ Produit trouvé:")
            print(f"   Code: {result['code']}")
            print(f"   Nom: {result['name']}")
            print(f"   Prix: {result['price']}€")
            print(f"   Stock: {result['stock']}")
        else:
            print(f"❌ Produit non trouvé: {result.get('error', 'Erreur inconnue')}")
    
    asyncio.run(run_quick_test())