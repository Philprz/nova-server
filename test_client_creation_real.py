#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test de création client réelle - VERSION FINALE CORRIGÉE
Correction des doublons Salesforce et champ Industry SAP
"""

import sys
import os
import asyncio
import json
import re
import time
import uuid
from datetime import datetime

# Ajouter le répertoire racine au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from services.mcp_connector import MCPConnector
    print("✅ MCPConnector importé avec succès")
except ImportError as e:
    print(f"❌ Erreur import MCPConnector: {e}")
    sys.exit(1)

# Générer un nom vraiment unique pour éviter les doublons
unique_id = str(uuid.uuid4())[:8]
timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')

# Données de test FINALES - TOUTES ERREURS CORRIGÉES
TEST_CLIENT_DATA = {
    "company_name": f"NOVA-TEST-{unique_id}-{timestamp}",  # Nom vraiment unique
    "industry": "Technology",
    "phone": "+33 1 23 45 67 89",
    "email": f"contact-{unique_id}@novatest.com",  # Email unique
    "website": f"https://www.novatest-{unique_id}.com",  # URL unique
    "annual_revenue": 1000000,
    "employees_count": 50,
    "description": f"Client de test NOVA - ID: {unique_id}",
    
    # Adresse de facturation
    "billing_street": f"123 Rue Test {unique_id}",
    "billing_city": "Paris",
    "billing_postal_code": "75001",
    "billing_country": "France",
    
    # Adresse de livraison
    "shipping_street": f"456 Avenue Livraison {unique_id}",
    "shipping_city": "Lyon",  
    "shipping_postal_code": "69001",
    "shipping_country": "France"
}

async def test_create_salesforce_client():
    """Test création client dans Salesforce - GESTION DES DOUBLONS"""
    print("\n=== TEST CRÉATION CLIENT SALESFORCE (FINAL) ===")
    
    try:
        # Préparer les données Salesforce
        sf_data = {
            "Name": TEST_CLIENT_DATA["company_name"],
            "Type": "Customer", 
            "Industry": TEST_CLIENT_DATA["industry"],
            "Phone": TEST_CLIENT_DATA["phone"],
            "Website": TEST_CLIENT_DATA["website"],
            "AnnualRevenue": TEST_CLIENT_DATA["annual_revenue"],
            "NumberOfEmployees": TEST_CLIENT_DATA["employees_count"],
            "Description": TEST_CLIENT_DATA["description"],
            "BillingStreet": TEST_CLIENT_DATA["billing_street"],
            "BillingCity": TEST_CLIENT_DATA["billing_city"],
            "BillingPostalCode": TEST_CLIENT_DATA["billing_postal_code"],
            "BillingCountry": TEST_CLIENT_DATA["billing_country"],
            "ShippingStreet": TEST_CLIENT_DATA["shipping_street"],
            "ShippingCity": TEST_CLIENT_DATA["shipping_city"],
            "ShippingPostalCode": TEST_CLIENT_DATA["shipping_postal_code"],
            "ShippingCountry": TEST_CLIENT_DATA["shipping_country"]
        }
        
        print(f"Création du client: {sf_data['Name']}")
        print("✨ Nom unique généré pour éviter les doublons")
        
        # Créer dans Salesforce
        result = await MCPConnector.call_salesforce_mcp("salesforce_create_record", {
            "sobject": "Account",
            "data": sf_data
        })
        
        # Gérer le cas de doublon détecté
        if not result.get("success") and "DUPLICATES_DETECTED" in str(result.get("error", "")):
            print("⚠️ Doublon détecté par Salesforce")
            print("🔄 Tentative avec un nom encore plus unique...")
            
            # Générer un nom encore plus unique
            extra_unique = str(int(time.time()))[-6:]
            sf_data["Name"] = f"{sf_data['Name']}-{extra_unique}"
            sf_data["Description"] = f"{sf_data['Description']} - Extra ID: {extra_unique}"
            
            print(f"Nouveau nom: {sf_data['Name']}")
            
            # Nouvelle tentative
            result = await MCPConnector.call_salesforce_mcp("salesforce_create_record", {
                "sobject": "Account",
                "data": sf_data
            })
        
        if result.get("success"):
            print("✅ Client Salesforce créé avec succès!")
            print(f"   ID: {result.get('id')}")
            print(f"   Nom: {sf_data['Name']}")
            
            # Vérifier la création
            verify_result = await MCPConnector.call_salesforce_mcp("salesforce_query", {
                "query": f"SELECT Id, Name, Type, Industry, Phone, BillingCity FROM Account WHERE Id = '{result.get('id')}'"
            })
            
            if "error" not in verify_result and verify_result.get("totalSize", 0) > 0:
                created_account = verify_result["records"][0]
                print("✅ Vérification OK:")
                print(f"   - Nom: {created_account.get('Name')}")
                print(f"   - Type: {created_account.get('Type')}")
                print(f"   - Industrie: {created_account.get('Industry')}")
                print(f"   - Téléphone: {created_account.get('Phone')}")
                print(f"   - Ville: {created_account.get('BillingCity')}")
                
                return {"success": True, "id": result.get("id"), "data": created_account, "final_name": sf_data['Name']}
            else:
                print("⚠️ Création réussie mais vérification échouée")
                return {"success": True, "id": result.get("id"), "verification_failed": True, "final_name": sf_data['Name']}
        else:
            print(f"❌ Erreur création Salesforce: {result.get('error')}")
            return {"success": False, "error": result.get("error")}
            
    except Exception as e:
        print(f"❌ Exception création Salesforce: {str(e)}")
        return {"success": False, "error": str(e)}

async def test_create_sap_client(salesforce_client_data=None):
    """Test création client dans SAP - CHAMPS CORRECTS"""
    print("\n=== TEST CRÉATION CLIENT SAP (FINAL) ===")
    
    try:
        # Générer un CardCode unique
        clean_name = re.sub(r'[^a-zA-Z0-9]', '', TEST_CLIENT_DATA["company_name"])[:8]
        timestamp = str(int(time.time()))[-4:]
        card_code = f"C{clean_name}{timestamp}".upper()[:15]
        
        # Préparer les données SAP - CHAMPS CORRECTS UNIQUEMENT
        sap_data = {
            "CardCode": card_code,
            "CardName": TEST_CLIENT_DATA["company_name"],
            "CardType": "cCustomer",
            "GroupCode": 100,  # Code de groupe par défaut
            "Currency": "EUR",
            "Valid": "tYES",
            "Frozen": "tNO"
        }
        
        # Ajouter SEULEMENT les champs optionnels compatibles
        if TEST_CLIENT_DATA.get("phone"):
            sap_data["Phone1"] = TEST_CLIENT_DATA["phone"][:20]
        
        if TEST_CLIENT_DATA.get("website"):
            sap_data["Website"] = TEST_CLIENT_DATA["website"][:100]
            
        if TEST_CLIENT_DATA.get("description"):
            sap_data["Notes"] = TEST_CLIENT_DATA["description"][:254]
        
        # CORRECTION IMPORTANTE: NE PAS inclure Industry car il faut un nombre
        # Dans SAP, Industry doit être un code numérique de secteur d'activité
        # Nous l'omettons pour ce test
        
        # Référence croisée Salesforce si disponible
        if salesforce_client_data and salesforce_client_data.get("id"):
            sap_data["FederalTaxID"] = salesforce_client_data["id"][:32]
        
        print(f"Création du client SAP: {card_code} - {sap_data['CardName']}")
        print("✅ Champ Industry supprimé (doit être numérique)")
        print(f"Données SAP: {json.dumps(sap_data, indent=2)}")
        
        # Créer dans SAP
        result = await MCPConnector.call_sap_mcp("sap_create_customer_complete", {
            "customer_data": sap_data
        })
        
        if result.get("success"):
            print("✅ Client SAP créé avec succès!")
            print(f"   CardCode: {card_code}")
            print(f"   CardName: {sap_data['CardName']}")
            print(f"   Créé: {'Oui' if result.get('created') else 'Existait déjà'}")
            
            # Vérifier la création
            verify_result = await MCPConnector.call_sap_mcp("sap_read", {
                "endpoint": f"/BusinessPartners('{card_code}')",
                "method": "GET"
            })
            
            if "error" not in verify_result:
                print("✅ Vérification SAP OK:")
                print(f"   - CardCode: {verify_result.get('CardCode')}")
                print(f"   - CardName: {verify_result.get('CardName')}")
                print(f"   - CardType: {verify_result.get('CardType')}")
                print(f"   - Currency: {verify_result.get('Currency')}")
                print(f"   - Phone1: {verify_result.get('Phone1', 'N/A')}")
                
                return {"success": True, "card_code": card_code, "data": verify_result}
            else:
                print("⚠️ Création réussie mais vérification échouée")
                print(f"Erreur vérification: {verify_result.get('error')}")
                return {"success": True, "card_code": card_code, "verification_failed": True}
        else:
            print(f"❌ Erreur création SAP: {result.get('error')}")
            return {"success": False, "error": result.get("error")}
            
    except Exception as e:
        print(f"❌ Exception création SAP: {str(e)}")
        return {"success": False, "error": str(e)}

async def test_complete_client_creation():
    """Test création client complète - VERSION FINALE"""
    print("\n=== TEST CRÉATION CLIENT COMPLÈTE (FINAL) ===")
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "client_data": TEST_CLIENT_DATA,
        "unique_id": unique_id,
        "salesforce_result": None,
        "sap_result": None,
        "success": False,
        "corrections_applied": [
            "Nom unique avec UUID pour éviter les doublons Salesforce",
            "Suppression du champ Industry pour SAP (doit être numérique)",
            "Utilisation uniquement des champs SAP validés",
            "Gestion automatique des doublons avec retry"
        ]
    }
    
    # 1. Créer dans Salesforce
    sf_result = await test_create_salesforce_client()
    results["salesforce_result"] = sf_result
    
    # 2. Créer dans SAP (avec référence Salesforce)
    sap_result = await test_create_sap_client(sf_result if sf_result.get("success") else None)
    results["sap_result"] = sap_result
    
    # 3. Évaluer le succès global
    sf_success = sf_result.get("success", False)
    sap_success = sap_result.get("success", False)
    
    if sf_success and sap_success:
        results["success"] = True
        print("\n🎉 CRÉATION CLIENT COMPLÈTE RÉUSSIE!")
        print(f"   Salesforce ID: {sf_result.get('id')}")
        print(f"   Salesforce Nom: {sf_result.get('final_name', 'N/A')}")
        print(f"   SAP CardCode: {sap_result.get('card_code')}")
        print("   Référence croisée: ✅")
    elif sf_success or sap_success:
        results["success"] = "partial"
        print("\n⚠️ CRÉATION PARTIELLE:")
        print(f"   Salesforce: {'✅' if sf_success else '❌'}")
        print(f"   SAP: {'✅' if sap_success else '❌'}")
        if sf_success:
            print(f"   Salesforce ID: {sf_result.get('id')}")
        if sap_success:
            print(f"   SAP CardCode: {sap_result.get('card_code')}")
    else:
        results["success"] = False
        print("\n❌ ÉCHEC CRÉATION CLIENT")
        print("Erreurs à analyser dans le fichier de résultats")
    
    # Sauvegarder les résultats détaillés
    result_file = f"test_client_creation_final_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    try:
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        print(f"\n📁 Résultats détaillés sauvegardés: {result_file}")
    except Exception as e:
        print(f"⚠️ Impossible de sauvegarder les résultats: {e}")
    
    return results

async def main():
    """Fonction principale de test"""
    print("🚀 TEST DE CRÉATION CLIENT RÉELLE - VERSION FINALE")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"ID Unique: {unique_id}")
    print(f"Client de test: {TEST_CLIENT_DATA['company_name']}")
    
    print("\n🔧 CORRECTIONS FINALES APPLIQUÉES:")
    print("   1. Nom unique avec UUID pour éviter les doublons")
    print("   2. Suppression du champ Industry SAP (doit être numérique)")
    print("   3. Gestion automatique des doublons avec retry")
    print("   4. Utilisation uniquement des champs validés")
    
    # Lancer le test complet
    results = await test_complete_client_creation()
    
    print("\n" + "="*60)
    print("📊 RÉSUMÉ FINAL")
    print("="*60)
    
    if results["success"] is True:
        print("🎯 ✅ SUCCÈS COMPLET - Client créé dans Salesforce ET SAP")
        print("\n🚀 PROCHAINES ÉTAPES:")
        print("  → ✅ Flux de création client validé")
        print("  → 🔄 Intégrer dans le workflow de devis")
        print("  → 🔄 Tester via l'API FastAPI /create_client") 
        print("  → 🔄 Tester le workflow complet avec création client automatique")
    elif results["success"] == "partial":
        print("⚠️ SUCCÈS PARTIEL - Client créé dans un seul système")
        print("\n🔍 À ANALYSER:")
        print("  → Vérifier les logs pour le système en échec")
        print("  → Corriger les erreurs restantes")
    else:
        print("❌ ÉCHEC - Aucune création réussie")
        print("\n🔧 À CORRIGER:")
        print("  → Analyser les erreurs dans le fichier de résultats")
        print("  → Vérifier les permissions et configurations")

if __name__ == "__main__":
    asyncio.run(main())