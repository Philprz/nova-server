#!/usr/bin/env python3
"""
Script de diagnostic pour débugger la recherche de produits SAP
Identifie pourquoi "Imprimante 20 ppm" n'est pas trouvé
"""

import asyncio
import json
import sys
from typing import Dict, Any, List
import logging

# Configuration du logging détaillé
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

sys.path.append('.')
from services.mcp_connector import MCPConnector


async def diagnose_product_search():
    """
    Diagnostic complet de la recherche de produits
    """
    print("\n" + "="*80)
    print("🔍 DIAGNOSTIC DE RECHERCHE PRODUITS SAP")
    print("="*80)
    
    connector = MCPConnector()
    
    # 1. Test de connexion SAP
    print("\n1️⃣ TEST DE CONNEXION SAP")
    print("-"*40)
    try:
        test_result = await connector.call_sap_mcp("sap_read", {
            "endpoint": "/Items?$top=1",
            "method": "GET"
        })
        if "error" not in test_result:
            print("✅ Connexion SAP fonctionnelle")
        else:
            print(f"❌ Erreur de connexion: {test_result['error']}")
            return
    except Exception as e:
        print(f"❌ Exception: {str(e)}")
        return
        
    # 2. Récupérer quelques produits pour voir la structure
    print("\n2️⃣ STRUCTURE DES PRODUITS SAP")
    print("-"*40)
    try:
        sample_result = await connector.call_sap_mcp("sap_read", {
            "endpoint": "/Items?$top=5&$orderby=ItemCode",
            "method": "GET"
        })
        
        if "value" in sample_result and sample_result["value"]:
            product = sample_result["value"][0]
            print(f"✅ Exemple de produit avec {len(product)} champs:")
            for key, value in sorted(product.items())[:15]:  # Afficher les 15 premiers champs
                print(f"   - {key}: {value}")
        else:
            print("❌ Aucun produit trouvé dans SAP")
            return
            
    except Exception as e:
        print(f"❌ Erreur: {str(e)}")
        
    # 3. Rechercher des imprimantes de différentes façons
    print("\n3️⃣ RECHERCHE D'IMPRIMANTES")
    print("-"*40)
    
    search_terms = [
        "printer", "Printer", "PRINTER",
        "imprimante", "Imprimante", "IMPRIMANTE",
        "print", "Print", "PRINT",
        "ppm", "PPM", "20 ppm", "20ppm"
    ]
    
    for term in search_terms:
        print(f"\n🔎 Recherche de '{term}':")
        
        # Recherche dans ItemName
        try:
            result = await connector.call_sap_mcp("sap_read", {
                "endpoint": f"/Items?$filter=contains(ItemName,'{term}')&$top=3",
                "method": "GET"
            })
            
            count = len(result.get("value", []))
            print(f"   Dans ItemName: {count} résultat(s)")
            
            if count > 0:
                for i, prod in enumerate(result["value"][:3], 1):
                    print(f"      {i}. [{prod.get('ItemCode')}] {prod.get('ItemName')}")
                    
        except Exception as e:
            print(f"   Erreur ItemName: {str(e)}")
            
        # Recherche dans U_Description si existe
        try:
            result = await connector.call_sap_mcp("sap_read", {
                "endpoint": f"/Items?$filter=contains(U_Description,'{term}')&$top=3",
                "method": "GET"
            })
            
            count = len(result.get("value", []))
            if count > 0:
                print(f"   Dans U_Description: {count} résultat(s)")
                for i, prod in enumerate(result["value"][:3], 1):
                    print(f"      {i}. [{prod.get('ItemCode')}] {prod.get('U_Description', 'N/A')}")
                    
        except Exception as e:
            # Ignorer si U_Description n'existe pas
            pass
            
    # 4. Analyser les groupes de produits
    print("\n4️⃣ GROUPES DE PRODUITS (ItemsGroupCode)")
    print("-"*40)
    
    try:
        # Récupérer des produits avec leurs groupes
        groups_result = await connector.call_sap_mcp("sap_read", {
            "endpoint": "/Items?$select=ItemCode,ItemName,ItemsGroupCode&$top=100",
            "method": "GET"
        })
        
        if "value" in groups_result:
            # Compter les groupes
            groups = {}
            for prod in groups_result["value"]:
                group = prod.get("ItemsGroupCode", "Sans groupe")
                groups[group] = groups.get(group, 0) + 1
                
            print(f"✅ {len(groups)} groupes trouvés:")
            for group, count in sorted(groups.items(), key=lambda x: x[1], reverse=True)[:10]:
                print(f"   - Groupe {group}: {count} produits")
                
            # Chercher un groupe qui pourrait contenir des imprimantes
            print("\n🔍 Recherche de groupes potentiels pour imprimantes:")
            for group in groups:
                if any(term in str(group).lower() for term in ["print", "imprim", "bureau", "office"]):
                    print(f"   ➡️ Groupe potentiel: {group}")
                    
    except Exception as e:
        print(f"❌ Erreur analyse groupes: {str(e)}")
        
    # 5. Recherche avec différentes méthodes de filtre
    print("\n5️⃣ TESTS DE FILTRES AVANCÉS")
    print("-"*40)
    
    # Test avec tolower pour être insensible à la casse
    try:
        result = await connector.call_sap_mcp("sap_read", {
            "endpoint": "/Items?$filter=contains(tolower(ItemName),'printer')&$top=5",
            "method": "GET"
        })
        
        if "value" in result:
            print(f"✅ Recherche case-insensitive: {len(result['value'])} résultats")
        else:
            print("❌ La fonction tolower() n'est peut-être pas supportée")
            
    except Exception as e:
        print(f"⚠️ tolower() non supporté: {str(e)}")
        
    # 6. Vérifier s'il y a des champs personnalisés pour les caractéristiques
    print("\n6️⃣ CHAMPS PERSONNALISÉS (U_*)")
    print("-"*40)
    
    try:
        # Récupérer un produit avec tous ses champs
        full_product = await connector.call_sap_mcp("sap_read", {
            "endpoint": "/Items?$top=1",
            "method": "GET"
        })
        
        if "value" in full_product and full_product["value"]:
            u_fields = [k for k in full_product["value"][0].keys() if k.startswith("U_")]
            print(f"✅ {len(u_fields)} champs personnalisés trouvés:")
            for field in u_fields[:10]:
                value = full_product["value"][0].get(field)
                print(f"   - {field}: {value}")
                
    except Exception as e:
        print(f"❌ Erreur: {str(e)}")
        
    # 7. Suggestions finales
    print("\n7️⃣ RECOMMANDATIONS")
    print("-"*40)
    print("📌 Pour trouver 'Imprimante 20 ppm', essayez:")
    print("   1. Vérifier le nom exact dans SAP Business One")
    print("   2. Utiliser le code article si connu")
    print("   3. Chercher par groupe de produits")
    print("   4. Vérifier si '20 ppm' est dans un champ personnalisé")
    print("   5. Contacter l'administrateur SAP pour confirmer l'existence du produit")
    

async def search_specific_product(product_name: str):
    """
    Recherche spécifique d'un produit avec toutes les méthodes possibles
    """
    print(f"\n🎯 RECHERCHE SPÉCIFIQUE: '{product_name}'")
    print("="*60)
    
    connector = MCPConnector()
    results = []
    
    # Différentes stratégies de recherche
    strategies = [
        {
            "name": "Recherche exacte",
            "filter": f"ItemName eq '{product_name}'"
        },
        {
            "name": "Contient (sensible casse)",
            "filter": f"contains(ItemName,'{product_name}')"
        },
        {
            "name": "Contient (mots séparés)",
            "filter": " and ".join([f"contains(ItemName,'{word}')" for word in product_name.split()])
        },
        {
            "name": "Recherche par mots-clés",
            "filter": " or ".join([f"contains(ItemName,'{word}')" for word in product_name.split() if len(word) > 3])
        }
    ]
    
    for strategy in strategies:
        print(f"\n🔍 {strategy['name']}:")
        print(f"   Filtre: {strategy['filter']}")
        
        try:
            result = await connector.call_sap_mcp("sap_read", {
                "endpoint": f"/Items?$filter={strategy['filter']}&$top=5",
                "method": "GET"
            })
            
            if "error" in result:
                print(f"   ❌ Erreur: {result['error']}")
            else:
                products = result.get("value", [])
                print(f"   ✅ {len(products)} résultat(s)")
                for prod in products:
                    print(f"      - [{prod.get('ItemCode')}] {prod.get('ItemName')}")
                    if prod.get('U_Description'):
                        print(f"        Description: {prod.get('U_Description')}")
                        
                if products:
                    results.extend(products)
                    
        except Exception as e:
            print(f"   ❌ Exception: {str(e)}")
            
    # Résumé
    print("\n📊 RÉSUMÉ DE LA RECHERCHE:")
    unique_codes = set()
    for r in results:
        unique_codes.add(r.get('ItemCode'))
        
    print(f"   Total de produits uniques trouvés: {len(unique_codes)}")
    
    return results


async def main():
    """
    Fonction principale
    """
    # Diagnostic général
    await diagnose_product_search()
    
    # Recherche spécifique du produit problématique
    await search_specific_product("Imprimante 20 ppm")
    
    print("\n✅ Diagnostic terminé\n")


if __name__ == "__main__":
    asyncio.run(main())