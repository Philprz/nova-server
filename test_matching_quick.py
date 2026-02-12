"""Test rapide du matching intelligent - 3 produits"""
import asyncio
from services.email_matcher import get_email_matcher

async def test():
    print("Initialisation...")
    matcher = get_email_matcher()
    await matcher.ensure_cache()
    print(f"Cache charge: {len(matcher._clients_cache)} clients, {len(matcher._items_cache)} produits\n")

    # Test simple avec 3 produits
    email_text = """
De: msezen@marmaracam.com.tr
Sujet: Demande de devis

Bonjour,

Pourriez-vous me faire un devis pour:

SHEPPEE CODE: HST-117-03 - SIZE 3 PUSHER BLADE CARBON - 50 Adet
SHEPPEE CODE: TRI-037 - LIFT ROLLER STUD - 2 Adet
SHEPPEE CODE: C315-6305RS - BALL BEARING - 2 Adet

Merci,
Marmara Cam
"""

    print("="*70)
    print("TEST MATCHING - 3 PRODUITS SHEPPEE")
    print("="*70)

    result = await matcher.match_email(
        body=email_text,
        sender_email="msezen@marmaracam.com.tr",
        subject="Demande de devis"
    )

    # Client
    print("\n[CLIENT]")
    if result.best_client:
        print(f"  Trouve: {result.best_client.card_name} ({result.best_client.card_code})")
        print(f"  Score: {result.best_client.score}")
    else:
        print("  NON TROUVE")

    # Produits
    print(f"\n[PRODUITS] {len(result.products)} produit(s)")
    for i, p in enumerate(result.products, 1):
        print(f"\n  {i}. {p.item_code}")
        print(f"     Nom: {p.item_name[:60]}")
        print(f"     Quantite: {p.quantity}")
        print(f"     Score: {p.score}")
        print(f"     Raison: {p.match_reason}")
        if p.not_found_in_sap:
            print(f"     Statut: NON TROUVE SAP - A CREER")
        elif p.score == 100:
            print(f"     Statut: EXACT MATCH")
        elif p.score >= 70:
            print(f"     Statut: FUZZY MATCH - A VALIDER")

    # Mapping DB
    from services.product_mapping_db import get_product_mapping_db
    mapping_db = get_product_mapping_db()
    stats = mapping_db.get_statistics()

    print(f"\n[APPRENTISSAGE]")
    print(f"  Total mappings: {stats['total']}")
    print(f"  Pending: {stats['pending']}")
    print(f"  Validated: {stats['validated']}")

    print("\n" + "="*70)

if __name__ == "__main__":
    asyncio.run(test())
