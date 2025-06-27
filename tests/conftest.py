# tests/conftest.py
"""
Configuration globale pour les tests pytest
Correction du PYTHONPATH pour importer les modules
"""

import pytest
import asyncio
import os
import sys

# CORRECTION CRITIQUE : Ajouter le répertoire racine au path
# On remonte d'un niveau depuis le dossier tests/ vers la racine du projet
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

    