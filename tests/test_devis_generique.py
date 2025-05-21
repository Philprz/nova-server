#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test générique du workflow de devis NOVA
Ce script teste le workflow complet à travers les étapes suivantes :
1. Extraction des informations à partir d'une demande en langage naturel
2. Validation du client dans Salesforce
3. Création du client dans SAP si nécessaire (via sap_create_customer)
4. Vérification de la disponibilité des produits
5. Création du devis
"""

import os
import sys
import sys
# Ajouter le répertoire parent (racine du projet) au chemin d'importation
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
# Maintenant l'import de workflow devrait fonctionner
from workflow.devis_workflow import DevisWorkflow

import json
import logging
import asyncio
from datetime import datetime

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"logs/test_devis_{datetime.now().strftime('%Y%m%d%H%M%S')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("test_devis")

async def test_workflow(prompt=None):
    """
    Teste le workflow de devis avec une demande en langage naturel
    
    Args:
        prompt: Demande en langage naturel (si None, l'utilisateur sera invité à en saisir une)
    """
    # Si aucun prompt n'est fourni, demander à l'utilisateur
    if prompt is None:
        print("\n=== TEST DU WORKFLOW DE DEVIS NOVA ===\n")
        print("Entrez une demande de devis en langage naturel")
        print("Exemple: 'faire un devis pour 500 ref A00002 pour le client Edge Communications'")
        print("Exemple: 'devis pour Salesforce Inc avec 10 unités de A00001'")
        prompt = input("\nVotre demande : ")
    
    print(f"\nTraitement de la demande : {prompt}\n")
    logger.info(f"Test du workflow avec la demande : {prompt}")
    
    # Initialiser le workflow
    workflow = DevisWorkflow()
    
    # Lancer le traitement
    start_time = datetime.now()
    try:
        result = await workflow.process_prompt(prompt)
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        
        # Enregistrer le résultat dans un fichier JSON
        output_file = f"test_result_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        # Afficher le résumé
        print("\n=== RÉSULTAT DU WORKFLOW ===")
        print(f"Temps de traitement : {processing_time:.2f} secondes")
        
        if result.get("status") == "success":
            print(f"✅ Workflow réussi")
            print(f"ID Devis        : {result.get('quote_id')}")
            print(f"Client          : {result.get('client', {}).get('name')}")
            print(f"Statut devis    : {result.get('quote_status')}")
            print(f"Montant total   : {result.get('total_amount')} {result.get('currency')}")
            
            # Afficher les produits
            print("\nProduits :")
            for idx, product in enumerate(result.get("products", []), 1):
                print(f"  {idx}. {product.get('name')} (Ref: {product.get('code')})")
                print(f"     Quantité : {product.get('quantity')}")
                print(f"     Prix     : {product.get('unit_price')} {result.get('currency')}")
                print(f"     Total    : {product.get('line_total')} {result.get('currency')}")
            
            # Vérifier les produits indisponibles
            if not result.get("all_products_available", True):
                print("\n⚠️ Certains produits sont indisponibles :")
                for prod in result.get("unavailable_products", []):
                    print(f"  - {prod.get('name')} (Ref: {prod.get('code')})")
                    print(f"    Demandé : {prod.get('quantity_requested')}, Disponible : {prod.get('quantity_available')}")
                
                # Afficher les alternatives si disponibles
                if result.get("alternatives"):
                    print("\nAlternatives disponibles :")
                    for prod_code, alternatives in result.get("alternatives", {}).items():
                        print(f"  Pour {prod_code} :")
                        for alt in alternatives:
                            print(f"    - {alt.get('ItemName')} (Ref: {alt.get('ItemCode')})")
                            print(f"      Prix : {alt.get('Price')}, Stock : {alt.get('Stock')}")
        else:
            print(f"❌ Workflow échoué")
            print(f"Message : {result.get('message')}")
            print(f"Détails :\n{json.dumps(result, indent=2)}")
        
        print(f"\nRésultat détaillé enregistré dans : {output_file}")
        
        return result
        
    except Exception as e:
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        logger.exception(f"Erreur lors du test du workflow : {str(e)}")
        print(f"\n❌ Erreur lors du test du workflow : {str(e)}")
        print(f"Temps écoulé : {processing_time:.2f} secondes")
        return {"status": "error", "message": str(e)}

async def main():
    """Fonction principale"""
    # Vérifier si un prompt est fourni en argument
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
    else:
        prompt = None
    
    await test_workflow(prompt)

if __name__ == "__main__":
    asyncio.run(main())