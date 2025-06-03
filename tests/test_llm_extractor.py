# tests/test_llm_extractor.py
"""
Tests unitaires pour LLMExtractor
Version complète avec mocks et cas limites
"""

import pytest
import json
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from services.llm_extractor import LLMExtractor


class TestLLMExtractor:
    """Tests unitaires pour la classe LLMExtractor"""
    
    @pytest.fixture
    def sample_prompts(self):
        """Données de test pour les prompts"""
        return {
            "simple_valid": "faire un devis pour 100 ref A00001 pour le client Edge Communications",
            "multiple_products": "devis pour le client SAFRAN avec 50 A00001 et 75 ref A00002",
            "english": "quote for 200 items A00001 for customer Edge Communications",
            "complex": "Bonjour, pouvez-vous me faire un devis pour la fourniture de 500 unités de référence A00002 pour notre client Edge Communications s'il vous plaît ?",
            "no_client": "faire un devis pour 100 ref A00001",
            "no_products": "faire un devis pour le client Edge Communications",
            "invalid": "bonjour comment allez-vous ?",
            "empty": "",
            "special_chars": "devis pour client ACME & Co. avec 100 réf A00001-X"
        }
    
    @pytest.fixture
    def expected_extractions(self):
        """Résultats attendus pour les extractions"""
        return {
            "simple_valid": {
                "client": "Edge Communications",
                "products": [{"code": "A00001", "quantity": 100}]
            },
            "multiple_products": {
                "client": "SAFRAN", 
                "products": [
                    {"code": "A00001", "quantity": 50},
                    {"code": "A00002", "quantity": 75}
                ]
            },
            "english": {
                "client": "Edge Communications",
                "products": [{"code": "A00001", "quantity": 200}]
            }
        }
    
    @pytest.fixture
    def mock_claude_response(self):
        """Réponse simulée de l'API Claude"""
        def create_response(client, products):
            return {
                "content": [
                    {
                        "text": json.dumps({
                            "client": client,
                            "products": products
                        })
                    }
                ]
            }
        return create_response
    
    @pytest.mark.asyncio
    async def test_extract_quote_info_success(self, sample_prompts, expected_extractions, mock_claude_response):
        """Test extraction réussie avec prompt valide"""
        prompt = sample_prompts["simple_valid"]
        expected = expected_extractions["simple_valid"]
        
        # Mock de la réponse API Claude
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_claude_response(
            expected["client"], 
            expected["products"]
        )
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            result = await LLMExtractor.extract_quote_info(prompt)
            
            assert result["client"] == expected["client"]
            assert len(result["products"]) == len(expected["products"])
            assert result["products"][0]["code"] == expected["products"][0]["code"]
            assert result["products"][0]["quantity"] == expected["products"][0]["quantity"]
    
    @pytest.mark.asyncio
    async def test_extract_multiple_products(self, sample_prompts, expected_extractions, mock_claude_response):
        """Test extraction avec plusieurs produits"""
        prompt = sample_prompts["multiple_products"]
        expected = expected_extractions["multiple_products"]
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_claude_response(
            expected["client"],
            expected["products"]
        )
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            result = await LLMExtractor.extract_quote_info(prompt)
            
            assert result["client"] == expected["client"]
            assert len(result["products"]) == 2
            assert result["products"][0]["code"] == "A00001"
            assert result["products"][0]["quantity"] == 50
            assert result["products"][1]["code"] == "A00002"
            assert result["products"][1]["quantity"] == 75
    
    @pytest.mark.asyncio
    async def test_extract_english_prompt(self, sample_prompts, expected_extractions, mock_claude_response):
        """Test extraction avec prompt en anglais"""
        prompt = sample_prompts["english"]
        expected = expected_extractions["english"]
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_claude_response(
            expected["client"],
            expected["products"]
        )
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            result = await LLMExtractor.extract_quote_info(prompt)
            
            assert result["client"] == expected["client"]
            assert result["products"][0]["quantity"] == 200
    
    @pytest.mark.asyncio
    async def test_api_error_handling(self, sample_prompts):
        """Test gestion des erreurs API Claude"""
        prompt = sample_prompts["simple_valid"]
        
        # Mock d'une erreur HTTP 500
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"error": "Internal Server Error"}
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            result = await LLMExtractor.extract_quote_info(prompt)
            
            assert "error" in result
            assert "Erreur API Claude" in result["error"]
    
    @pytest.mark.asyncio 
    async def test_api_timeout_handling(self, sample_prompts):
        """Test gestion du timeout API"""
        prompt = sample_prompts["simple_valid"]
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.TimeoutException("Request timeout")
            )
            
            result = await LLMExtractor.extract_quote_info(prompt)
            
            assert "error" in result
            assert "timeout" in result["error"].lower()
    
    @pytest.mark.asyncio
    async def test_invalid_json_response(self, sample_prompts):
        """Test gestion d'une réponse JSON invalide"""
        prompt = sample_prompts["simple_valid"]
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": [{"text": "Ceci n'est pas du JSON valide"}]
        }
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            result = await LLMExtractor.extract_quote_info(prompt)
            
            assert "error" in result
            assert "Format de réponse invalide" in result["error"]
    
    @pytest.mark.asyncio
    async def test_missing_content_in_response(self, sample_prompts):
        """Test gestion d'une réponse sans contenu"""
        prompt = sample_prompts["simple_valid"]
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"usage": {"tokens": 100}}  # Pas de "content"
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            result = await LLMExtractor.extract_quote_info(prompt)
            
            assert "error" in result
            assert "contenu manquant" in result["error"]
    
    @pytest.mark.asyncio
    async def test_empty_prompt(self, sample_prompts):
        """Test avec prompt vide"""
        prompt = sample_prompts["empty"]
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": [{"text": '{"client": "", "products": []}'}]
        }
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            result = await LLMExtractor.extract_quote_info(prompt)
            
            # Le système doit gérer gracieusement les prompts vides
            assert "client" in result
            assert "products" in result
    
    @pytest.mark.asyncio
    async def test_special_characters_handling(self, sample_prompts):
        """Test gestion des caractères spéciaux"""
        prompt = sample_prompts["special_chars"]
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": [{"text": '{"client": "ACME & Co.", "products": [{"code": "A00001-X", "quantity": 100}]}'}]
        }
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            result = await LLMExtractor.extract_quote_info(prompt)
            
            assert result["client"] == "ACME & Co."
            assert result["products"][0]["code"] == "A00001-X"
    
    @pytest.mark.asyncio
    async def test_api_key_configuration(self, sample_prompts):
        """Test vérification de la configuration de la clé API"""
        prompt = sample_prompts["simple_valid"]
        
        with patch.dict('os.environ', {}, clear=True):  # Pas de clé API
            with patch('httpx.AsyncClient') as mock_client:
                # Le test devrait échouer car pas de clé API
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                    side_effect=Exception("API key not configured")
                )
                
                result = await LLMExtractor.extract_quote_info(prompt)
                
                assert "error" in result
    
    @pytest.mark.asyncio 
    async def test_large_prompt_handling(self):
        """Test gestion d'un prompt très long"""
        # Créer un prompt très long (> 1000 caractères)
        long_prompt = "faire un devis pour le client Edge Communications avec " + \
                     " et ".join([f"100 ref A{i:05d}" for i in range(1, 100)])
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": [{"text": '{"client": "Edge Communications", "products": [{"code": "A00001", "quantity": 100}]}'}]
        }
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            result = await LLMExtractor.extract_quote_info(long_prompt)
            
            # Le système doit traiter même les longs prompts
            assert "client" in result
            assert result["client"] == "Edge Communications"


class TestLLMExtractorIntegration:
    """Tests d'intégration pour LLMExtractor"""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_real_api_call(self):
        """Test d'intégration réel avec l'API Claude (si clé disponible)"""
        import os
        
        if not os.getenv("ANTHROPIC_API_KEY"):
            pytest.skip("ANTHROPIC_API_KEY non configurée - test d'intégration ignoré")
        
        prompt = "faire un devis pour 10 ref A00001 pour le client Test"
        result = await LLMExtractor.extract_quote_info(prompt)
        
        # Vérifications basiques sur le résultat réel
        assert isinstance(result, dict)
        if "error" not in result:
            assert "client" in result
            assert "products" in result


# Configuration pytest
def pytest_configure(config):
    """Configuration pytest pour les tests LLMExtractor"""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (may be slow)"
    )