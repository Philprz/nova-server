"""
Test du pricing automatique Phase 5
Verifie que le pricing fonctionne correctement
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_pricing():
    print("=" * 80)
    print("TEST PRICING AUTOMATIQUE - PHASE 5")
    print("=" * 80)
    print()

    from services.pricing_engine import get_pricing_engine
    from services.pricing_models import PricingContext

    pricing_engine = get_pricing_engine()

    # Test avec un produit exemple
    print("[TEST] Test pricing pour produit MOT-5KW...")
    print("-" * 80)

    context = PricingContext(
        item_code="MOT-5KW",
        card_code="C00001",
        quantity=5,
        supplier_price=None,  # Sera recupere automatiquement
        apply_margin=45.0,
        force_recalculate=False
    )

    try:
        result = await pricing_engine.calculate_price(context)

        if result.success and result.decision:
            d = result.decision
            print(f"[OK] SUCCES")
            print(f"   CAS: {d.case_type.value}")
            print(f"   Prix calcule: {d.calculated_price:.2f} EUR")
            if d.supplier_price:
                print(f"   Prix fournisseur: {d.supplier_price:.2f} EUR")
            print(f"   Marge: {d.margin_applied:.0f}%")
            print(f"   Total ligne (x{context.quantity}): {d.calculated_price * context.quantity:.2f} EUR")
            print(f"   Confiance: {d.confidence_score:.1%}")
            print(f"   Validation requise: {'OUI' if d.requires_validation else 'NON'}")

            if d.alerts:
                print(f"   [ALERTES]:")
                for alert in d.alerts:
                    print(f"      - {alert}")

            print(f"   Justification: {d.justification[:150]}...")
            print(f"   Temps: {result.processing_time_ms:.0f}ms")
        else:
            print(f"[ERREUR] {result.error}")

    except Exception as e:
        print(f"[EXCEPTION] {e}")
        import traceback
        traceback.print_exc()

    print()
    print("=" * 80)
    print("FIN DU TEST")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_pricing())
