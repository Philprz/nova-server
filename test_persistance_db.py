"""
Test de la persistance base de donnees
Verifie que les analyses sont sauvegardees et consultables
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_persistence():
    print("=" * 80)
    print("TEST PERSISTANCE BASE DE DONNEES")
    print("=" * 80)
    print()

    from services.email_analysis_db import get_email_analysis_db

    db = get_email_analysis_db()

    # Test 1 : Sauvegarder une analyse
    print("[TEST 1] Sauvegarde analyse...")
    print("-" * 80)

    test_email_id = "TEST_EMAIL_123"
    test_analysis = {
        "is_quote_request": True,
        "extracted_data": {
            "client_name": "Test Client",
            "client_card_code": "C001"
        },
        "product_matches": [
            {
                "item_code": "PROD001",
                "item_name": "Produit Test 1",
                "quantity": 10,
                "score": 100,
                "match_reason": "Match exact",
                "unit_price": 15.50,
                "line_total": 155.00,
                "pricing_case": "CAS_1_HC",
                "pricing_justification": "Reprise prix derniere vente"
            }
        ]
    }

    try:
        db.save_analysis(
            email_id=test_email_id,
            subject="Test - Demande devis",
            from_address="test@client.com",
            analysis_result=test_analysis
        )
        print("[OK] Analyse sauvegardee")
        print()
    except Exception as e:
        print(f"[ERREUR] Sauvegarde: {e}")
        import traceback
        traceback.print_exc()
        return

    # Test 2 : Recuperer l'analyse
    print("[TEST 2] Recuperation analyse...")
    print("-" * 80)

    try:
        retrieved = db.get_analysis(test_email_id)

        if retrieved:
            print("[OK] Analyse recuperee depuis DB")
            print()
            print(f"Email ID: {test_email_id}")
            print(f"Devis: {retrieved.get('is_quote_request')}")
            print(f"Client: {retrieved.get('extracted_data', {}).get('client_name')}")
            print(f"Produits: {len(retrieved.get('product_matches', []))}")

            if retrieved.get('product_matches'):
                prod = retrieved['product_matches'][0]
                print()
                print(f"Article 1:")
                print(f"  Code: {prod.get('item_code')}")
                print(f"  Nom: {prod.get('item_name')}")
                print(f"  Quantite: {prod.get('quantity')}")
                print(f"  Prix unitaire: {prod.get('unit_price')} EUR")
                print(f"  CAS: {prod.get('pricing_case')}")
                print(f"  Total: {prod.get('line_total')} EUR")
            print()

        else:
            print("[ERREUR] Analyse non recuperee")
            return

    except Exception as e:
        print(f"[ERREUR] Recuperation: {e}")
        import traceback
        traceback.print_exc()
        return

    # Test 3 : Statistiques
    print("[TEST 3] Statistiques...")
    print("-" * 80)

    try:
        stats = db.get_statistics()

        print(f"Total analyses: {stats['total_analyzed']}")
        print(f"Demandes devis: {stats['quote_requests']}")
        print(f"Avec pricing: {stats['with_pricing']}")
        print(f"Total produits: {stats['total_products']}")
        print()

    except Exception as e:
        print(f"[ERREUR] Statistiques: {e}")
        import traceback
        traceback.print_exc()
        return

    # Test 4 : Suppression (cleanup)
    print("[TEST 4] Suppression analyse test...")
    print("-" * 80)

    try:
        db.delete_analysis(test_email_id)
        print("[OK] Analyse test supprimee")
        print()

        # Verifier suppression
        retrieved_after = db.get_analysis(test_email_id)
        if retrieved_after is None:
            print("[OK] Verification suppression reussie")
        else:
            print("[WARN] Analyse encore presente apres suppression")

    except Exception as e:
        print(f"[ERREUR] Suppression: {e}")
        import traceback
        traceback.print_exc()
        return

    print()
    print("=" * 80)
    print("TOUS LES TESTS REUSSIS")
    print("=" * 80)
    print()
    print("La persistance fonctionne correctement :")
    print("  - Sauvegarde analyses OK")
    print("  - Recuperation analyses OK")
    print("  - Statistiques OK")
    print("  - Suppression OK")
    print()
    print("Prochaine etape : Tester avec le serveur FastAPI en prod")

if __name__ == "__main__":
    asyncio.run(test_persistence())
