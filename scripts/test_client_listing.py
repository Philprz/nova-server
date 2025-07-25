# scripts/test_client_listing.py - SCRIPT DE TEST DIRECT

"""
Script pour tester directement les fonctions de listing
"""

import asyncio
import logging
import sys
import os

# Ajouter le chemin du projet
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.client_lister import list_all_clients, find_client_everywhere

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_listing():
    """Test complet du listing"""
    print("=" * 60)
    print("TEST LISTING COMPLET DES CLIENTS")
    print("=" * 60)
    
    try:
        # Test 1: Listing complet
        print("\n1. LISTING COMPLET")
        result = await list_all_clients()
        
        print(f"Total clients: {result['summary']['total_combined']}")
        print(f"  - Salesforce: {result['summary']['salesforce']['total']}")
        print(f"  - SAP: {result['summary']['sap']['total']}")
        
        # Afficher quelques noms Salesforce
        print("\nÉchantillon Salesforce:")
        for name in result['summary']['salesforce']['names'][:5]:
            print(f"  - {name}")
        
        # Afficher quelques noms SAP
        print("\nÉchantillon SAP:")
        for name in result['summary']['sap']['names'][:5]:
            print(f"  - {name}")
        
        # Test 2: Recherche RONDOT
        print("\n" + "=" * 40)
        print("2. RECHERCHE SPÉCIFIQUE - RONDOT")
        print("=" * 40)
        
        rondot_result = await find_client_everywhere("RONDOT")
        
        print(f"RONDOT trouvé: {rondot_result['total_found']} fois")
        
        if rondot_result["salesforce"]["found"]:
            print("\nDans Salesforce:")
            for client in rondot_result["salesforce"]["clients"]:
                print(f"  - {client.get('Name')} (ID: {client.get('Id')})")
        else:
            print("\nPas trouvé dans Salesforce")
        
        if rondot_result["sap"]["found"]:
            print("\nDans SAP:")
            for client in rondot_result["sap"]["clients"]:
                print(f"  - {client.get('CardName')} (Code: {client.get('CardCode')})")
        else:
            print("\nPas trouvé dans SAP")
        
        # Test 3: Recherches variantes
        print("\n" + "=" * 40)
        print("3. RECHERCHES VARIANTES")
        print("=" * 40)
        
        variants = ["rondot", "Rondot", "RONDOT", "rond"]
        
        for variant in variants:
            print(f"\nRecherche '{variant}':")
            variant_result = await find_client_everywhere(variant)
            print(f"  Trouvé: {variant_result['total_found']} fois")
            
            if variant_result['total_found'] > 0:
                if variant_result["salesforce"]["found"]:
                    sf_names = [c.get('Name') for c in variant_result["salesforce"]["clients"]]
                    print(f"  SF: {sf_names}")
                if variant_result["sap"]["found"]:
                    sap_names = [c.get('CardName') for c in variant_result["sap"]["clients"]]
                    print(f"  SAP: {sap_names}")
        
        print("\n" + "=" * 60)
        print("TEST TERMINÉ AVEC SUCCÈS")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ ERREUR DURANT LE TEST: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Exécuter le test
    asyncio.run(test_listing())