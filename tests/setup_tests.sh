#!/bin/bash
# setup_tests.sh - Script de mise en place de la structure de tests

echo "🧪 Configuration de la structure de tests NOVA"

# Créer la structure des dossiers de tests
mkdir -p tests/{unit,integration,fixtures}
mkdir -p tests/unit/{services,workflow,routes}
mkdir -p tests/integration/{api,database,mcp}

# Créer le fichier __init__.py pour les tests
touch tests/__init__.py
touch tests/unit/__init__.py
touch tests/integration/__init__.py
touch tests/fixtures/__init__.py

# Créer les fichiers de configuration de test
cat > tests/conftest.py << 'EOF'
# tests/conftest.py
"""
Configuration globale pour les tests pytest
"""

import pytest
import asyncio
import os
import sys
from unittest.mock import MagicMock, AsyncMock

# Ajouter le répertoire racine au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@pytest.fixture(scope="session")
def event_loop():
    """Fixture pour la boucle d'événements asyncio"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def mock_env_vars(monkeypatch):
    """Fixture pour mocker les variables d'environnement"""
    test_env = {
        "ANTHROPIC_API_KEY": "test-key-123",
        "SALESFORCE_USERNAME": "test@example.com",
        "SALESFORCE_PASSWORD": "testpass",
        "SALESFORCE_SECURITY_TOKEN": "testtoken",
        "SAP_REST_BASE_URL": "https://test-sap:50000/b1s/v1",
        "SAP_USER": "testuser",
        "SAP_CLIENT_PASSWORD": "testpass",
        "SAP_CLIENT": "TESTDB",
        "API_KEY": "test-api-key"
    }
    
    for key, value in test_env.items():
        monkeypatch.setenv(key, value)
    
    return test_env

@pytest.fixture
def mock_mcp_connector():
    """Fixture pour mocker MCPConnector"""
    with pytest.mock.patch('services.mcp_connector.MCPConnector') as mock:
        # Configuration des méthodes de base
        mock.call_salesforce_mcp = AsyncMock()
        mock.call_sap_mcp = AsyncMock()
        mock.salesforce_create_record = AsyncMock()
        mock.sap_create_customer_complete = AsyncMock()
        yield mock

@pytest.fixture
def sample_client_data():
    """Données client de test"""
    return {
        "company_name": "Test Company",
        "phone": "+33 1 23 45 67 89",
        "email": "contact@testcompany.com",
        "billing_street": "123 Rue de Test",
        "billing_city": "Paris",
        "billing_postal_code": "75001",
        "billing_country": "France",
        "industry": "Technology"
    }

@pytest.fixture
def sample_product_data():
    """Données produit de test"""
    return [
        {
            "code": "A00001",
            "quantity": 10,
            "name": "Product A",
            "unit_price": 100.0,
            "stock": 50
        },
        {
            "code": "A00002", 
            "quantity": 5,
            "name": "Product B",
            "unit_price": 200.0,
            "stock": 25
        }
    ]

@pytest.fixture
def sample_salesforce_response():
    """Réponse Salesforce de test"""
    return {
        "totalSize": 1,
        "records": [
            {
                "Id": "0014000000Test1",
                "Name": "Test Company",
                "AccountNumber": "ACC001",
                "Phone": "+33 1 23 45 67 89",
                "BillingCity": "Paris",
                "BillingCountry": "France"
            }
        ]
    }

@pytest.fixture
def sample_sap_response():
    """Réponse SAP de test"""
    return {
        "value": [
            {
                "ItemCode": "A00001",
                "ItemName": "Product A",
                "Price": 100.0,
                "QuantityOnStock": 50,
                "OnHand": 50
            }
        ]
    }
EOF

# Créer un fichier de test d'exemple pour vérifier la configuration
cat > tests/test_config.py << 'EOF'
# tests/test_config.py
"""
Test de configuration de base pour vérifier que pytest fonctionne
"""

import pytest

def test_pytest_working():
    """Test basique pour vérifier que pytest fonctionne"""
    assert True

@pytest.mark.asyncio
async def test_async_support():
    """Test pour vérifier le support asyncio"""
    import asyncio
    await asyncio.sleep(0.01)
    assert True

def test_fixtures(sample_client_data, sample_product_data):
    """Test pour vérifier que les fixtures fonctionnent"""
    assert sample_client_data["company_name"] == "Test Company"
    assert len(sample_product_data) == 2
    assert sample_product_data[0]["code"] == "A00001"

class TestConfiguration:
    """Tests de configuration"""
    
    def test_environment_variables(self, mock_env_vars):
        """Test que les variables d'environnement sont mockées"""
        import os
        assert os.getenv("ANTHROPIC_API_KEY") == "test-key-123"
        assert os.getenv("SALESFORCE_USERNAME") == "test@example.com"
    
    @pytest.mark.unit
    def test_unit_marker(self):
        """Test que les marqueurs fonctionnent"""
        assert True
    
    @pytest.mark.integration 
    def test_integration_marker(self):
        """Test que les marqueurs d'intégration fonctionnent"""
        assert True
EOF

# Créer les fichiers __init__.py dans les sous-dossiers
touch tests/unit/services/__init__.py
touch tests/unit/workflow/__init__.py
touch tests/unit/routes/__init__.py
touch tests/integration/api/__init__.py
touch tests/integration/database/__init__.py
touch tests/integration/mcp/__init__.py

echo "✅ Structure de tests créée:"
echo "📁 tests/"
echo "├── conftest.py (configuration globale)"
echo "├── test_config.py (tests de base)"
echo "├── unit/"
echo "│   ├── services/ (tests services)"
echo "│   ├── workflow/ (tests workflow)"
echo "│   └── routes/ (tests API)"
echo "├── integration/"
echo "│   ├── api/ (tests API externes)"
echo "│   ├── database/ (tests DB)"
echo "│   └── mcp/ (tests MCP)"
echo "└── fixtures/ (données de test)"

echo ""
echo "🚀 Pour installer pytest et les dépendances de test:"
echo "pip install pytest pytest-asyncio pytest-mock pytest-cov pytest-timeout"

echo ""
echo "🧪 Pour lancer les tests:"
echo "pytest                           # Tous les tests"
echo "pytest -m unit                   # Tests unitaires seulement"
echo "pytest -m integration            # Tests d'intégration seulement"
echo "pytest tests/test_config.py      # Test de configuration"
echo "pytest --cov                     # Avec couverture de code"