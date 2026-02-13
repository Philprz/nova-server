"""
Test pricing avec un vrai produit SAP
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_real_pricing():
    print("=" * 80)
    print("TEST PRICING AVEC PRODUIT REEL")
    print("=" * 80)
    print()

    from services.sap_business_service import get_sap_business_service
    from services.pricing_engine import get_pricing_engine
    from services.pricing_models import PricingContext

    sap_service = get_sap_business_service()
    pricing_engine = get_pricing_engine()

    # 1. Recuperer quelques produits SAP
    print("[1] Recuperation produits SAP...")
    print("-" * 80)

    try:
        items = await sap_service.search_items("", top=5)

        if not items:
            print("[ERREUR] Aucun produit trouve dans SAP")
            return

        print(f"[OK] {len(items)} produits trouves:")
        for i, item in enumerate(items, 1):
            print(f"   {i}. {item.ItemCode} - {item.ItemName}")

        # Prendre le premier produit
        test_item = items[0]
        print()
        print(f"[TEST] Produit selectionne: {test_item.ItemCode}")
        print()

    except Exception as e:
        print(f"[ERREUR] Recuperation SAP: {e}")
        import traceback
        traceback.print_exc()
        return

    # 2. Recuperer un client
    print("[2] Recherche client...")
    print("-" * 80)

    try:
        # Chercher un client
        from services.sap_cache_db import get_sap_cache_db
        cache_db = get_sap_cache_db()

        # Recuperer 1 client au hasard
        import sqlite3
        conn = sqlite3.connect(cache_db.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT CardCode, CardName FROM clients LIMIT 1")
        row = cursor.fetchone()
        conn.close()

        if row:
            card_code, card_name = row
            print(f"[OK] Client trouve: {card_name} ({card_code})")
        else:
            print("[WARN] Aucun client trouve, utilisation CardCode UNKNOWN")
            card_code = "UNKNOWN"

        print()

    except Exception as e:
        print(f"[WARN] Erreur recuperation client: {e}")
        card_code = "UNKNOWN"

    # 3. Tester pricing
    print("[3] TEST PRICING")
    print("=" * 80)

    context = PricingContext(
        item_code=test_item.ItemCode,
        card_code=card_code,
        quantity=10,
        supplier_price=None,
        apply_margin=45.0,
        force_recalculate=False
    )

    try:
        result = await pricing_engine.calculate_price(context)

        if result.success and result.decision:
            d = result.decision
            print(f"[OK] SUCCES !")
            print()
            print(f"Produit: {test_item.ItemCode} - {test_item.ItemName}")
            print(f"Client: {card_code}")
            print(f"Quantite: {context.quantity}")
            print()
            print(f">>> CAS APPLIQUE: {d.case_type.value} <<<")
            print(f"    Description: {d.case_description}")
            print()
            print(f"PRIX:")
            print(f"    Prix unitaire: {d.calculated_price:.2f} EUR")
            if d.supplier_price:
                print(f"    Prix fournisseur: {d.supplier_price:.2f} EUR")
            print(f"    Marge appliquee: {d.margin_applied:.1f}%")
            print(f"    Total ligne: {d.line_total:.2f} EUR")
            print()
            print(f"QUALITE:")
            print(f"    Confiance: {d.confidence_score:.0%}")
            print(f"    Validation requise: {'OUI' if d.requires_validation else 'NON'}")
            if d.validation_reason:
                print(f"    Raison: {d.validation_reason}")
            print()

            if d.alerts:
                print(f"ALERTES:")
                for alert in d.alerts:
                    print(f"    ! {alert}")
                print()

            if d.last_sale_date:
                print(f"HISTORIQUE:")
                print(f"    Derniere vente: {d.last_sale_date}")
                print(f"    Prix precedent: {d.last_sale_price:.2f} EUR")
                if d.last_sale_doc_num:
                    print(f"    Document: {d.last_sale_doc_num}")
                print()

            print(f"JUSTIFICATION:")
            print(f"    {d.justification}")
            print()

            print(f"PERFORMANCE:")
            print(f"    Temps calcul: {result.processing_time_ms:.0f}ms")
            print()

        else:
            print(f"[ERREUR] Pricing echoue: {result.error}")

    except Exception as e:
        print(f"[EXCEPTION] {e}")
        import traceback
        traceback.print_exc()

    print("=" * 80)
    print("FIN DU TEST")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_real_pricing())
