"""Test simple du matching MarmaraCam"""
import asyncio
import sys
from services.email_matcher import get_email_matcher

async def test():
    matcher = get_email_matcher()

    print("Chargement cache...")
    await matcher.ensure_cache()
    print(f"Clients: {len(matcher._clients_cache)}")
    print(f"Produits: {len(matcher._items_cache)}")

    # Chercher MARMARA CAM dans le cache
    print("\nRecherche MARMARA CAM dans le cache...")
    for client in matcher._clients_cache:
        if "MARMARA" in client.get("CardName", "").upper():
            print(f"  Trouve: {client.get('CardCode')} - {client.get('CardName')}")

    print("\n" + "="*60)
    print("TESTS MATCHING")
    print("="*60)

    tests = [
        "Demande chiffrage MARMARA CAM",
        "Demande chiffrage MarmaraCam",
        "Demande chiffrage pour Marmara Cam",
        "Client : marmaracam",
    ]

    for body in tests:
        print(f"\nTexte: '{body}'")

        result = await matcher.match_email(
            body=body,
            sender_email="test@example.com",
            subject=""
        )

        if result.best_client:
            print(f"  MATCH: {result.best_client.card_name} ({result.best_client.card_code})")
            print(f"  Score: {result.best_client.score}")
            print(f"  Raison: {result.best_client.match_reason}")
        else:
            print(f"  PAS DE MATCH")

if __name__ == "__main__":
    try:
        asyncio.run(test())
    except Exception as e:
        print(f"ERREUR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
