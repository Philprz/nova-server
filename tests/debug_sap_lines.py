# tests/debug_sap_lines.py
"""
Script pour diagnostiquer le problème de récupération des lignes SAP
"""

import os
import sys
import asyncio
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.mcp_connector import MCPConnector

async def debug_sap_quotation_lines(doc_entry: int = 367):
    """Debug spécifique pour les lignes du devis SAP"""
    print(f"=== DEBUG LIGNES DEVIS SAP {doc_entry} ===")
    
    try:
        # 1. Vérifier le devis principal
        print("1. Vérification du devis principal...")
        quotation = await MCPConnector.call_sap_mcp("sap_read", {
            "endpoint": f"/Quotations({doc_entry})",
            "method": "GET"
        })
        
        if "error" in quotation:
            print(f"❌ Erreur devis principal: {quotation['error']}")
            return
        
        print(f"✅ Devis trouvé: DocNum {quotation.get('DocNum')}")
        print(f"   Total: {quotation.get('DocTotal')} {quotation.get('DocCurrency')}")
        
        # 2. Vérifier les lignes avec différentes approches
        print("\n2. Test récupération lignes - Approche 1...")
        lines_v1 = await MCPConnector.call_sap_mcp("sap_read", {
            "endpoint": f"/Quotations({doc_entry})/DocumentLines",
            "method": "GET"
        })
        
        print(f"Résultat approche 1: {type(lines_v1)}")
        if "error" in lines_v1:
            print(f"❌ Erreur: {lines_v1['error']}")
        elif "value" in lines_v1:
            print(f"✅ {len(lines_v1['value'])} lignes trouvées")
            for i, line in enumerate(lines_v1['value'][:2]):  # Afficher max 2 lignes
                print(f"   Ligne {i+1}: {line.get('ItemCode')} - {line.get('ItemDescription')} - Qty: {line.get('Quantity')}")
        else:
            print(f"Structure inattendue: {list(lines_v1.keys())}")
        
        # 3. Test approche alternative
        print("\n3. Test récupération - Approche 2 (requête directe)...")
        lines_v2 = await MCPConnector.call_sap_mcp("sap_read", {
            "endpoint": f"/Quotations?$filter=DocEntry eq {doc_entry}&$expand=DocumentLines",
            "method": "GET"
        })
        
        if "error" in lines_v2:
            print(f"❌ Erreur approche 2: {lines_v2['error']}")
        elif "value" in lines_v2 and lines_v2["value"]:
            doc_lines = lines_v2["value"][0].get("DocumentLines", [])
            print(f"✅ Approche 2: {len(doc_lines)} lignes dans DocumentLines")
            for i, line in enumerate(doc_lines[:2]):
                print(f"   Ligne {i+1}: {line.get('ItemCode')} - {line.get('ItemDescription')} - Qty: {line.get('Quantity')}")
        
        # 4. Vérifier si les lignes sont dans le devis principal
        print("\n4. Vérification lignes dans devis principal...")
        if "DocumentLines" in quotation:
            doc_lines = quotation["DocumentLines"]
            print(f"✅ {len(doc_lines)} lignes trouvées dans le devis principal!")
            for i, line in enumerate(doc_lines):
                print(f"   Ligne {i+1}:")
                print(f"     - ItemCode: {line.get('ItemCode')}")
                print(f"     - Description: {line.get('ItemDescription')}")
                print(f"     - Quantité: {line.get('Quantity')}")
                print(f"     - Prix: {line.get('Price')}")
                print(f"     - Total ligne: {line.get('LineTotal')}")
                print(f"     - TVA: {line.get('VatGroup')} ({line.get('TaxPercentagePerRow')}%)")
        else:
            print("❌ Pas de DocumentLines dans le devis principal")
        
        # 5. Analyser la différence de montant
        print("\n5. Analyse des montants...")
        doc_total = float(quotation.get('DocTotal', 0))
        vat_sum = float(quotation.get('VatSum', 0))
        net_total = doc_total - vat_sum
        
        print(f"   - Total TTC (SAP): {doc_total}")
        print(f"   - TVA (SAP): {vat_sum}")
        print(f"   - Total HT (SAP): {net_total}")
        print(f"   - Total Salesforce: 100000.0 (probablement HT)")
        print(f"   - Cohérence HT: {'✅' if abs(net_total - 100000.0) < 0.01 else '❌'}")
        
        return {
            "quotation": quotation,
            "lines_found": len(quotation.get("DocumentLines", [])),
            "total_ttc": doc_total,
            "total_ht": net_total,
            "tva": vat_sum
        }
        
    except Exception as e:
        print(f"❌ Erreur: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return None

if __name__ == "__main__":
    result = asyncio.run(debug_sap_quotation_lines())
    if result:
        print(f"\n=== RÉSULTAT ===")
        print(f"Lignes trouvées: {result['lines_found']}")
        print(f"Total TTC: {result['total_ttc']}")
        print(f"Total HT: {result['total_ht']}")
        print(f"TVA: {result['tva']}")