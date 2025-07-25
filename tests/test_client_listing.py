# tests/test_client_listing.py - FICHIER DE TEST

"""
Tests pour les fonctions de listing des clients
"""
import sys
import os
import pytest
import asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.client_lister import list_all_clients, find_client_everywhere

@pytest.mark.asyncio
async def test_list_all_clients():
    """Test du listing complet"""
    result = await list_all_clients()
    
    assert "summary" in result
    assert "salesforce_clients" in result
    assert "sap_clients" in result
    assert result["summary"]["total_combined"] >= 0

@pytest.mark.asyncio 
async def test_find_rondot():
    """Test spécifique pour RONDOT"""
    result = await find_client_everywhere("RONDOT")
    
    assert "search_term" in result
    assert "salesforce" in result
    assert "sap" in result
    assert "total_found" in result
    
    print(f"RONDOT trouvé: {result['total_found']} fois")
    if result["salesforce"]["found"]:
        print(f"Salesforce: {result['salesforce']['clients']}")
    if result["sap"]["found"]:
        print(f"SAP: {result['sap']['clients']}")
