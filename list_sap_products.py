#!/usr/bin/env python3
"""
Script utilitaire pour lister tous les produits SAP avec leurs champs complets
Usage: python list_sap_products.py [--limit N] [--search TERM] [--format json|csv]
"""

import asyncio
import json
import csv
import sys
import argparse
from datetime import datetime
from typing import Dict, Any, List
import logging

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import du connecteur MCP
sys.path.append('.')
from services.mcp_connector import MCPConnector


async def get_all_sap_products(limit: int = 1000, search_term: str = None) -> Dict[str, Any]:
    """
    Récupère tous les produits SAP avec leurs détails complets
    
    Args:
        limit: Nombre maximum de produits à récupérer
        search_term: Terme de recherche optionnel
        
    Returns:
        Dict contenant les produits et métadonnées
    """
    try:
        connector = MCPConnector()
        
        # Construire le endpoint SAP
        endpoint = f"/Items?$top={limit}"
        
        # Ajouter filtre de recherche si spécifié
        if search_term:
            endpoint += f"&$filter=contains(ItemName,'{search_term}') or contains(ItemCode,'{search_term}')"
            
        # Ajouter tri par code produit
        endpoint += "&$orderby=ItemCode"
        
        logger.info(f"Appel SAP endpoint: {endpoint}")
        
        # Appel MCP SAP
        result = await connector.call_sap_mcp("sap_read", {
            "endpoint": endpoint,
            "method": "GET"
        })
        
        if "error" in result:
            logger.error(f"Erreur SAP: {result['error']}")
            return {"error": result["error"], "products": []}
            
        # Extraire les produits
        products = result.get("value", [])
        
        # Analyser les champs disponibles
        fields_summary = analyze_product_fields(products)
        
        return {
            "success": True,
            "count": len(products),
            "limit": limit,
            "search_term": search_term,
            "timestamp": datetime.now().isoformat(),
            "fields_summary": fields_summary,
            "products": products
        }
        
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des produits: {str(e)}")
        return {"error": str(e), "products": []}


def analyze_product_fields(products: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyse les champs présents dans les produits
    
    Args:
        products: Liste des produits
        
    Returns:
        Résumé des champs trouvés
    """
    if not products:
        return {"message": "Aucun produit trouvé"}
        
    # Collecter tous les champs uniques
    all_fields = set()
    field_types = {}
    field_examples = {}
    field_presence = {}
    
    for product in products:
        for field, value in product.items():
            all_fields.add(field)
            
            # Déterminer le type
            value_type = type(value).__name__
            if field not in field_types:
                field_types[field] = set()
            field_types[field].add(value_type)
            
            # Stocker un exemple non-nul
            if value is not None and field not in field_examples:
                field_examples[field] = value
                
            # Compter la présence
            if field not in field_presence:
                field_presence[field] = 0
            if value is not None:
                field_presence[field] += 1
    
    # Créer le résumé
    fields_info = {}
    for field in sorted(all_fields):
        fields_info[field] = {
            "types": list(field_types.get(field, [])),
            "example": field_examples.get(field),
            "presence_count": field_presence.get(field, 0),
            "presence_percentage": round(100 * field_presence.get(field, 0) / len(products), 2)
        }
        
    return {
        "total_fields": len(all_fields),
        "total_products": len(products),
        "fields": fields_info
    }


def format_products_csv(products: List[Dict[str, Any]], output_file: str = "sap_products.csv"):
    """
    Exporte les produits au format CSV
    """
    if not products:
        logger.warning("Aucun produit à exporter")
        return
        
    # Collecter tous les champs
    all_fields = set()
    for product in products:
        all_fields.update(product.keys())
    
    fields = sorted(all_fields)
    
    # Écrire le CSV
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(products)
        
    logger.info(f"Produits exportés vers {output_file}")


def display_products_summary(result: Dict[str, Any]):
    """
    Affiche un résumé des produits récupérés
    """
    if "error" in result:
        print(f"\n❌ ERREUR: {result['error']}\n")
        return
        
    print("\n" + "="*80)
    print(f"📦 PRODUITS SAP - RÉSUMÉ")
    print("="*80)
    print(f"✅ Nombre de produits récupérés: {result['count']}")
    print(f"📅 Date de récupération: {result['timestamp']}")
    
    if result.get('search_term'):
        print(f"🔍 Terme de recherche: {result['search_term']}")
        
    # Afficher le résumé des champs
    fields_summary = result.get('fields_summary', {})
    if fields_summary.get('fields'):
        print(f"\n📊 ANALYSE DES CHAMPS ({fields_summary['total_fields']} champs trouvés):")
        print("-"*80)
        
        # Trier par taux de présence décroissant
        sorted_fields = sorted(
            fields_summary['fields'].items(),
            key=lambda x: x[1]['presence_percentage'],
            reverse=True
        )
        
        for field_name, field_info in sorted_fields[:20]:  # Top 20 champs
            print(f"\n🔹 {field_name}:")
            print(f"   - Types: {', '.join(field_info['types'])}")
            print(f"   - Présence: {field_info['presence_percentage']}% ({field_info['presence_count']}/{fields_summary['total_products']})")
            if field_info['example'] is not None:
                example_str = str(field_info['example'])
                if len(example_str) > 100:
                    example_str = example_str[:100] + "..."
                print(f"   - Exemple: {example_str}")
                
    # Afficher quelques exemples de produits
    if result.get('products'):
        print(f"\n📋 EXEMPLES DE PRODUITS (10 premiers):")
        print("-"*80)
        
        for i, product in enumerate(result['products'][:10], 1):
            print(f"\n🔸 Produit #{i}:")
            print(f"   - Code: {product.get('ItemCode', 'N/A')}")
            print(f"   - Nom: {product.get('ItemName', 'N/A')}")
            print(f"   - Prix: {product.get('U_PrixCatalogue', product.get('Price', 'N/A'))}")
            print(f"   - Stock: {product.get('QuantityOnStock', product.get('OnHand', 'N/A'))}")
            print(f"   - Groupe: {product.get('ItemsGroupCode', 'N/A')}")
            
            # Afficher d'autres champs intéressants
            for field in ['U_Description', 'BarCode', 'ManufacturerName']:
                if field in product and product[field]:
                    print(f"   - {field}: {product[field]}")


async def main():
    """
    Fonction principale
    """
    parser = argparse.ArgumentParser(description='Liste tous les produits SAP avec leurs détails')
    parser.add_argument('--limit', type=int, default=100, help='Nombre maximum de produits (défaut: 100)')
    parser.add_argument('--search', type=str, help='Terme de recherche optionnel')
    parser.add_argument('--format', choices=['json', 'csv', 'summary'], default='summary', 
                       help='Format de sortie (défaut: summary)')
    parser.add_argument('--output', type=str, help='Fichier de sortie (pour json/csv)')
    
    args = parser.parse_args()
    
    print("\n🔄 Récupération des produits SAP en cours...")
    
    # Récupérer les produits
    result = await get_all_sap_products(limit=args.limit, search_term=args.search)
    
    # Traiter selon le format demandé
    if args.format == 'json':
        output_file = args.output or f"sap_products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"✅ Données exportées vers {output_file}")
        
    elif args.format == 'csv':
        if result.get('products'):
            output_file = args.output or f"sap_products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            format_products_csv(result['products'], output_file)
        else:
            print("❌ Aucun produit à exporter")
            
    else:  # summary
        display_products_summary(result)
    
    print("\n✅ Traitement terminé\n")


if __name__ == "__main__":
    asyncio.run(main())