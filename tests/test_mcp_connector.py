# tests/test_mcp_connector.py
"""
Tests unitaires pour MCPConnector
Module central d'intégration Salesforce/SAP via MCP
"""

import pytest
import json
from unittest.mock import patch, MagicMock, AsyncMock, mock_open
from services.mcp_connector import MCPConnector


class TestMCPConnectorCore:
    """Tests pour les fonctionnalités core de MCPConnector"""
    
    @pytest.fixture
    def sample_mcp_response(self):
        """Réponse MCP standard pour les tests"""
        return {
            "success": True,
            "id": "test_record_123",
            "data": {"Name": "Test Record"}
        }
    
    @pytest.fixture
    def sample_salesforce_query_response(self):
        """Réponse Salesforce query pour les tests"""
        return {
            "totalSize": 1,
            "records": [
                {
                    "Id": "0014000000Test1",
                    "Name": "Test Company",
                    "AccountNumber": "ACC001"
                }
            ]
        }
    
    @pytest.fixture
    def sample_sap_response(self):
        """Réponse SAP pour les tests"""
        return {
            "success": True,
            "doc_num": "367",
            "doc_entry": 123,
            "card_code": "C001"
        }
    
    @pytest.mark.asyncio
    async def test_call_mcp_success(self, sample_mcp_response):
        """Test appel MCP réussi"""
        with patch('subprocess.run') as mock_subprocess:
            with patch('tempfile.NamedTemporaryFile') as mock_temp:
                # Configuration des mocks
                mock_temp_file = MagicMock()
                mock_temp_file.name = "/tmp/test_input.json"
                mock_temp.return_value.__enter__.return_value = mock_temp_file
                
                # Mock subprocess success
                mock_subprocess.return_value.returncode = 0
                
                # Mock file reading
                with patch('builtins.open', mock_open(read_data=json.dumps(sample_mcp_response))):
                    with patch('os.path.exists', return_value=True):
                        with patch('asyncio.get_event_loop') as mock_loop:
                            mock_executor = MagicMock()
                            mock_executor.return_value = (0, "", "")
                            mock_loop.return_value.run_in_executor = AsyncMock(return_value=(0, "", ""))
                            
                            result = await MCPConnector._call_mcp("test_server", "test_action", {"param": "value"})
                            
                            assert result["success"] is True
                            assert result["id"] == "test_record_123"
    
    @pytest.mark.asyncio
    async def test_call_mcp_script_not_found(self):
        """Test appel MCP avec script inexistant"""
        with patch('os.path.exists', return_value=False):
            result = await MCPConnector._call_mcp("nonexistent_server", "test_action", {})
            
            assert "error" in result
            assert "Script MCP introuvable" in result["error"]
    
    @pytest.mark.asyncio
    async def test_call_mcp_subprocess_error(self):
        """Test appel MCP avec erreur subprocess"""
        with patch('os.path.exists', return_value=True):  # CORRECTION: Mock script exists
            with patch('subprocess.run') as mock_subprocess:
                with patch('tempfile.NamedTemporaryFile') as mock_temp:
                    mock_temp_file = MagicMock()
                    mock_temp_file.name = "/tmp/test_input.json"
                    mock_temp.return_value.__enter__.return_value = mock_temp_file
                    
                    # Mock subprocess error
                    mock_subprocess.return_value.returncode = 1
                    mock_subprocess.return_value.stderr = "Test error"
                    
                    with patch('asyncio.get_event_loop') as mock_loop:
                        mock_loop.return_value.run_in_executor = AsyncMock(return_value=(1, "", "Test error"))
                        
                        result = await MCPConnector._call_mcp("test_server", "test_action", {})
                        
                        assert "error" in result
                        assert "Échec appel MCP" in result["error"]
    
    @pytest.mark.asyncio
    async def test_call_mcp_timeout(self):
        """Test appel MCP avec timeout"""
        with patch('subprocess.run') as _:
            with patch('tempfile.NamedTemporaryFile') as mock_temp:
                mock_temp_file = MagicMock()
                mock_temp_file.name = "/tmp/test_input.json"
                mock_temp.return_value.__enter__.return_value = mock_temp_file
                
                with patch('asyncio.get_event_loop') as mock_loop:
                    mock_loop.return_value.run_in_executor = AsyncMock(return_value=(-1, "", "Timeout lors de l'exécution"))
                    
                    result = await MCPConnector._call_mcp("test_server", "test_action", {})
                    
                    assert "error" in result
                    assert "Échec appel MCP" in result["error"]
    
    @pytest.mark.asyncio
    async def test_call_mcp_file_cleanup_error(self):
        """Test nettoyage des fichiers temporaires avec erreur"""
        with patch('os.path.exists', return_value=True):
            with patch('os.path.dirname', return_value="/fake/path"):
                with patch('tempfile.NamedTemporaryFile') as mock_temp:
                    mock_temp_file = MagicMock()
                    mock_temp_file.name = "/tmp/test_input.json"
                    mock_temp.return_value.__enter__.return_value = mock_temp_file
                    
                    with patch('asyncio.get_event_loop') as mock_loop:
                        mock_loop.return_value.run_in_executor = AsyncMock(return_value=(0, "", ""))
                        
                        with patch('builtins.open', mock_open(read_data='{"success": true}')):
                            with patch('os.unlink', side_effect=OSError("Permission denied")):
                                result = await MCPConnector._call_mcp("test_server", "test_action", {})
                                
                                # Le test doit réussir malgré l'erreur de nettoyage
                                assert result["success"] is True
    
    @pytest.mark.asyncio
    async def test_call_mcp_missing_output_file(self):
        """Test appel MCP avec fichier de sortie manquant"""
        with patch('os.path.exists') as mock_exists:
            # Script existe, mais fichier de sortie n'existe pas
            mock_exists.side_effect = lambda path: "test_server.py" in path
            
            with patch('os.path.dirname', return_value="/fake/path"):
                with patch('tempfile.NamedTemporaryFile') as mock_temp:
                    mock_temp_file = MagicMock()
                    mock_temp_file.name = "/tmp/test_input.json"
                    mock_temp.return_value.__enter__.return_value = mock_temp_file
                    
                    with patch('asyncio.get_event_loop') as mock_loop:
                        mock_loop.return_value.run_in_executor = AsyncMock(return_value=(0, "", ""))
                        
                        result = await MCPConnector._call_mcp("test_server", "test_action", {})
                        
                        assert "error" in result
                        assert "Fichier de sortie MCP non créé" in result["error"]
    
    @pytest.mark.asyncio
    async def test_call_mcp_critical_exception(self):
        """Test exception critique lors de l'appel MCP"""
        with patch('tempfile.NamedTemporaryFile', side_effect=Exception("Critical error")):
            result = await MCPConnector._call_mcp("test_server", "test_action", {})
            
            assert "error" in result
            assert "Critical error" in result["error"]
        """Test appel MCP avec réponse JSON invalide"""
        with patch('subprocess.run') as mock_subprocess:
            with patch('tempfile.NamedTemporaryFile') as mock_temp:
                mock_temp_file = MagicMock()
                mock_temp_file.name = "/tmp/test_input.json"
                mock_temp.return_value.__enter__.return_value = mock_temp_file
                
                mock_subprocess.return_value.returncode = 0
                
                # Mock file with invalid JSON
                with patch('builtins.open', mock_open(read_data="invalid json")):
                    with patch('os.path.exists', return_value=True):
                        with patch('asyncio.get_event_loop') as mock_loop:
                            mock_loop.return_value.run_in_executor = AsyncMock(return_value=(0, "", ""))
                            
                            result = await MCPConnector._call_mcp("test_server", "test_action", {})
                            
                            assert "error" in result
                            assert "Format JSON invalide" in result["error"]


class TestMCPConnectorSalesforce:
    """Tests pour les méthodes Salesforce de MCPConnector"""
    
    @pytest.fixture
    def sample_salesforce_query_response(self):
        """Réponse Salesforce query pour les tests"""
        return {
            "totalSize": 1,
            "records": [
                {
                    "Id": "0014000000Test1",
                    "Name": "Test Company",
                    "AccountNumber": "ACC001"
                }
            ]
        }
    
    @pytest.mark.asyncio
    async def test_call_salesforce_mcp(self, sample_salesforce_query_response):
        """Test appel MCP Salesforce"""
        with patch.object(MCPConnector, '_call_mcp') as mock_call:
            mock_call.return_value = sample_salesforce_query_response
            
            result = await MCPConnector.call_salesforce_mcp("salesforce_query", {"query": "SELECT Id FROM Account"})
            
            mock_call.assert_called_once_with("salesforce_mcp", "salesforce_query", {"query": "SELECT Id FROM Account"})
            assert result["totalSize"] == 1
            assert len(result["records"]) == 1
    
    @pytest.mark.asyncio
    async def test_salesforce_create_record(self):
        """Test création d'enregistrement Salesforce"""
        expected_response = {"success": True, "id": "0014000000Test1"}
        
        with patch.object(MCPConnector, 'call_salesforce_mcp') as mock_call:
            mock_call.return_value = expected_response
            
            result = await MCPConnector.salesforce_create_record("Account", {"Name": "Test Company"})
            
            mock_call.assert_called_once_with("salesforce_create_record", {
                "sobject": "Account",
                "data": {"Name": "Test Company"}
            })
            assert result["success"] is True
            assert result["id"] == "0014000000Test1"
    
    @pytest.mark.asyncio
    async def test_salesforce_update_record(self):
        """Test mise à jour d'enregistrement Salesforce"""
        expected_response = {"success": True, "id": "0014000000Test1", "updated": True}
        
        with patch.object(MCPConnector, 'call_salesforce_mcp') as mock_call:
            mock_call.return_value = expected_response
            
            result = await MCPConnector.salesforce_update_record("Account", "0014000000Test1", {"Name": "Updated Name"})
            
            mock_call.assert_called_once_with("salesforce_update_record", {
                "sobject": "Account",
                "record_id": "0014000000Test1",
                "data": {"Name": "Updated Name"}
            })
            assert result["success"] is True
            assert result["updated"] is True
    
    @pytest.mark.asyncio
    async def test_salesforce_create_product_complete(self):
        """Test création produit complet Salesforce"""
        product_data = {"Name": "Test Product", "ProductCode": "PRD001"}
        expected_response = {
            "success": True,
            "product_id": "01t4000000Test1",
            "pricebook_entry_id": "01u4000000Test1"
        }
        
        with patch.object(MCPConnector, 'call_salesforce_mcp') as mock_call:
            mock_call.return_value = expected_response
            
            result = await MCPConnector.salesforce_create_product_complete(product_data, 100.0)
            
            mock_call.assert_called_once_with("salesforce_create_product_complete", {
                "product_data": product_data,
                "unit_price": 100.0
            })
            assert result["success"] is True
            assert "product_id" in result
    
    @pytest.mark.asyncio
    async def test_salesforce_create_opportunity_complete(self):
        """Test création opportunité complète Salesforce"""
        opportunity_data = {"Name": "Test Opportunity", "AccountId": "0014000000Test1"}
        line_items = [{"PricebookEntryId": "01u4000000Test1", "Quantity": 1}]
        
        expected_response = {
            "success": True,
            "opportunity_id": "0064000000Test1",
            "lines_count": 1
        }
        
        with patch.object(MCPConnector, 'call_salesforce_mcp') as mock_call:
            mock_call.return_value = expected_response
            
            result = await MCPConnector.salesforce_create_opportunity_complete(opportunity_data, line_items)
            
            mock_call.assert_called_once_with("salesforce_create_opportunity_complete", {
                "opportunity_data": opportunity_data,
                "line_items": line_items
            })
            assert result["success"] is True
            assert result["lines_count"] == 1
    
    @pytest.mark.asyncio
    async def test_salesforce_get_standard_pricebook(self):
        """Test récupération Pricebook standard"""
        expected_response = {
            "success": True,
            "pricebook_id": "01s4000000Test1",
            "pricebook_name": "Standard Price Book"
        }
        
        with patch.object(MCPConnector, 'call_salesforce_mcp') as mock_call:
            mock_call.return_value = expected_response
            
            result = await MCPConnector.salesforce_get_standard_pricebook()
            
            mock_call.assert_called_once_with("salesforce_get_standard_pricebook", {})
            assert result["success"] is True
            assert "pricebook_id" in result


class TestMCPConnectorSAP:
    """Tests pour les méthodes SAP de MCPConnector"""
    
    @pytest.fixture
    def sample_sap_response(self):
        """Réponse SAP pour les tests"""
        return {
            "success": True,
            "doc_num": "367",
            "doc_entry": 123,
            "card_code": "C001"
        }
    
    @pytest.mark.asyncio
    async def test_call_sap_mcp(self, sample_sap_response):
        """Test appel MCP SAP"""
        with patch.object(MCPConnector, '_call_mcp') as mock_call:
            mock_call.return_value = sample_sap_response
            
            result = await MCPConnector.call_sap_mcp("sap_read", {"endpoint": "/Items"})
            
            mock_call.assert_called_once_with("sap_mcp", "sap_read", {"endpoint": "/Items"})
            assert result["success"] is True
            assert result["doc_num"] == "367"
    
    @pytest.mark.asyncio
    async def test_sap_create_customer_complete(self):
        """Test création client complet SAP"""
        customer_data = {
            "CardCode": "C001",
            "CardName": "Test Customer",
            "CardType": "cCustomer"
        }
        
        expected_response = {
            "success": True,
            "created": True,
            "data": {"CardCode": "C001", "CardName": "Test Customer"}
        }
        
        with patch.object(MCPConnector, 'call_sap_mcp') as mock_call:
            mock_call.return_value = expected_response
            
            result = await MCPConnector.sap_create_customer_complete(customer_data)
            
            mock_call.assert_called_once_with("sap_create_customer_complete", {
                "customer_data": customer_data
            })
            assert result["success"] is True
            assert result["created"] is True
    
    @pytest.mark.asyncio
    async def test_sap_create_quotation_complete(self):
        """Test création devis complet SAP"""
        quotation_data = {
            "CardCode": "C001",
            "DocumentLines": [
                {"ItemCode": "A00001", "Quantity": 10, "Price": 100.0}
            ]
        }
        
        expected_response = {
            "success": True,
            "doc_num": "367",
            "doc_entry": 123,
            "total_amount": 1000.0
        }
        
        with patch.object(MCPConnector, 'call_sap_mcp') as mock_call:
            mock_call.return_value = expected_response
            
            result = await MCPConnector.sap_create_quotation_complete(quotation_data)
            
            mock_call.assert_called_once_with("sap_create_quotation_complete", {
                "quotation_data": quotation_data
            })
            assert result["success"] is True
            assert result["doc_num"] == "367"
    
    @pytest.mark.asyncio
    async def test_get_sap_product_details(self):
        """Test récupération détails produit SAP"""
        expected_response = {
            "ItemCode": "A00001",
            "ItemName": "Test Product",
            "Price": 100.0,
            "stock": {"total": 50}
        }
        
        with patch.object(MCPConnector, 'call_sap_mcp') as mock_call:
            mock_call.return_value = expected_response
            
            result = await MCPConnector.get_sap_product_details("A00001")
            
            mock_call.assert_called_once_with("sap_get_product_details", {
                "item_code": "A00001"
            })
            assert result["ItemCode"] == "A00001"
            assert result["Price"] == 100.0
    
    @pytest.mark.asyncio
    async def test_search_sap_entity(self):
        """Test recherche entité SAP"""
        expected_response = {
            "query": "test",
            "entity_type": "Items",
            "results": [{"ItemCode": "A00001", "ItemName": "Test Product"}],
            "count": 1
        }
        
        with patch.object(MCPConnector, 'call_sap_mcp') as mock_call:
            mock_call.return_value = expected_response
            
            result = await MCPConnector.search_sap_entity("test", "Items", 5)
            
            mock_call.assert_called_once_with("sap_search", {
                "query": "test",
                "entity_type": "Items",
                "limit": 5
            })
            assert result["count"] == 1
            assert len(result["results"]) == 1


class TestMCPConnectorUtilities:
    """Tests pour les méthodes utilitaires de MCPConnector"""
    
    @pytest.mark.asyncio
    async def test_verify_sap_quotation_with_doc_entry(self):
        """Test vérification devis SAP avec DocEntry"""
        expected_response = {
            "DocEntry": 123,
            "DocNum": "367",
            "CardCode": "C001"
        }
        
        with patch.object(MCPConnector, 'call_sap_mcp') as mock_call:
            mock_call.return_value = expected_response
            
            result = await MCPConnector.verify_sap_quotation(doc_entry=123)
            
            mock_call.assert_called_once_with("sap_read", {
                "endpoint": "/Quotations(123)",
                "method": "GET"
            })
            assert result["DocEntry"] == 123
    
    @pytest.mark.asyncio
    async def test_verify_sap_quotation_with_doc_num(self):
        """Test vérification devis SAP avec DocNum"""
        expected_response = {
            "value": [{
                "DocEntry": 123,
                "DocNum": "367",
                "CardCode": "C001"
            }]
        }
        
        with patch.object(MCPConnector, 'call_sap_mcp') as mock_call:
            mock_call.return_value = expected_response
            
            result = await MCPConnector.verify_sap_quotation(doc_num="367")
            
            mock_call.assert_called_once_with("sap_read", {
                "endpoint": "/Quotations?$filter=DocNum eq 367",
                "method": "GET"
            })
            assert result["value"][0]["DocNum"] == "367"
    
    @pytest.mark.asyncio
    async def test_verify_sap_quotation_no_params(self):
        """Test vérification devis SAP sans paramètres"""
        result = await MCPConnector.verify_sap_quotation()
        
        assert "error" in result
        assert "Doc_entry ou doc_num requis" in result["error"]
    
    @pytest.mark.asyncio
    async def test_verify_sap_customer(self):
        """Test vérification client SAP"""
        expected_response = {
            "CardCode": "C001",
            "CardName": "Test Customer",
            "CardType": "cCustomer"
        }
        
        with patch.object(MCPConnector, 'call_sap_mcp') as mock_call:
            mock_call.return_value = expected_response
            
            result = await MCPConnector.verify_sap_customer("C001")
            
            mock_call.assert_called_once_with("sap_read", {
                "endpoint": "/BusinessPartners('C001')",
                "method": "GET"
            })
            assert result["CardCode"] == "C001"
    
    @pytest.mark.asyncio
    async def test_test_connections(self):
        """Test diagnostic des connexions"""
        # Mock réponses pour les deux systèmes
        sf_response = {"totalSize": 1, "records": [{"Id": "test"}]}
        sap_response = "pong! Serveur MCP SAP opérationnel"
        
        with patch.object(MCPConnector, 'call_salesforce_mcp') as mock_sf:
            mock_sf.return_value = sf_response
            
            with patch.object(MCPConnector, 'call_sap_mcp') as mock_sap:
                mock_sap.return_value = sap_response
                
                result = await MCPConnector.test_connections()
                
                assert "salesforce" in result
                assert "sap" in result
                assert result["salesforce"]["connected"] is True
                assert result["sap"]["connected"] is True
    
    @pytest.mark.asyncio
    async def test_test_connections_with_errors(self):
        """Test diagnostic des connexions avec erreurs"""
        with patch.object(MCPConnector, 'call_salesforce_mcp') as mock_sf:
            mock_sf.return_value = {"error": "Connection failed"}
            
            with patch.object(MCPConnector, 'call_sap_mcp') as mock_sap:
                mock_sap.side_effect = Exception("SAP connection error")
                
                result = await MCPConnector.test_connections()
                
                assert result["salesforce"]["connected"] is False
                assert result["sap"]["connected"] is False
                assert "error" in result["sap"]
    
    @pytest.mark.asyncio
    async def test_get_recent_sap_data(self):
        """Test récupération données récentes SAP"""
        customers_response = {
            "value": [{"CardCode": "C001", "CardName": "Customer 1"}]
        }
        quotations_response = {
            "value": [{"DocEntry": 123, "DocNum": "367"}]
        }
        
        with patch.object(MCPConnector, 'call_sap_mcp') as mock_sap:
            mock_sap.side_effect = [customers_response, quotations_response]
            
            result = await MCPConnector.get_recent_sap_data(2)
            
            assert "recent_customers" in result
            assert "recent_quotations" in result
            assert len(result["recent_customers"]["value"]) == 1
            assert len(result["recent_quotations"]["value"]) == 1
    
    def test_is_connection_error(self):
        """Test détection d'erreurs de connexion"""
        # Test avec erreur de connexion
        connection_error = {"error": "Connection timeout"}
        assert MCPConnector.is_connection_error(connection_error) is True
        
        # Test avec autre erreur
        other_error = {"error": "Invalid data format"}
        assert MCPConnector.is_connection_error(other_error) is False
        
        # Test sans erreur
        success_result = {"success": True, "data": "test"}
        assert MCPConnector.is_connection_error(success_result) is False
    
    def test_extract_error_message_complex_cases(self):
        """Test extraction de messages d'erreur - cas complexes"""
        # Test erreur structurée avec message string
        sap_error_string = {
            "error": {
                "message": "Direct string message"
            }
        }
        assert MCPConnector.extract_error_message(sap_error_string) == "Direct string message"
        
        # Test erreur structurée avec nested error
        nested_error = {
            "error": {
                "error": "Nested error message"
            }
        }
        assert MCPConnector.extract_error_message(nested_error) == "Nested error message"
        
        # Test erreur avec objet complexe
        complex_error = {
            "error": {
                "code": 500,
                "details": "Complex error"
            }
        }
        result = MCPConnector.extract_error_message(complex_error)
        assert "code" in result or "details" in result
    
    @pytest.mark.asyncio
    async def test_get_recent_sap_data_with_error(self):
        """Test récupération données récentes SAP avec erreur"""
        with patch.object(MCPConnector, 'call_sap_mcp') as mock_sap:
            mock_sap.side_effect = Exception("SAP connection error")
            
            result = await MCPConnector.get_recent_sap_data(2)
            
            assert "error" in result
            assert "SAP connection error" in result["error"]


class TestMCPConnectorLegacy:
    """Tests pour les méthodes legacy/compatibilité de MCPConnector"""
    
    @pytest.mark.asyncio
    async def test_call_mcp_server_legacy(self):
        """Test méthode legacy call_mcp_server"""
        expected_response = {"success": True, "legacy": True}
        
        with patch.object(MCPConnector, '_call_mcp') as mock_call:
            mock_call.return_value = expected_response
            
            # Test de la méthode legacy
            result = await MCPConnector.call_mcp_server("test_server", "test_action", {"param": "value"})
            
            mock_call.assert_called_once_with("test_server", "test_action", {"param": "value"})
            assert result["success"] is True


# Tests d'intégration simplifiés
class TestMCPConnectorIntegration:
    """Tests d'intégration pour MCPConnector"""
    
    @pytest.mark.asyncio
    async def test_full_workflow_simulation(self):
        """Test simulation workflow complet"""
        # Simuler un workflow : recherche client -> création -> devis
        
        # 1. Recherche client Salesforce
        sf_search_response = {"totalSize": 0, "records": []}
        
        # 2. Création client SAP
        sap_create_response = {
            "success": True,
            "created": True,
            "data": {"CardCode": "C001", "CardName": "New Customer"}
        }
        
        # 3. Création devis SAP
        sap_quotation_response = {
            "success": True,
            "doc_num": "367",
            "doc_entry": 123
        }
        
        with patch.object(MCPConnector, 'call_salesforce_mcp') as mock_sf:
            mock_sf.return_value = sf_search_response
            
            with patch.object(MCPConnector, 'call_sap_mcp') as mock_sap:
                mock_sap.side_effect = [sap_create_response, sap_quotation_response]
                
                # Simuler les étapes
                search_result = await MCPConnector.call_salesforce_mcp("salesforce_query", {"query": "SELECT Id FROM Account"})
                assert search_result["totalSize"] == 0
                
                customer_result = await MCPConnector.call_sap_mcp("sap_create_customer_complete", {"customer_data": {}})
                assert customer_result["success"] is True
                
                quotation_result = await MCPConnector.call_sap_mcp("sap_create_quotation_complete", {"quotation_data": {}})
                assert quotation_result["success"] is True