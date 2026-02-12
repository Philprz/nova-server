#!/usr/bin/env python3
"""Test rapide du EmailMatcher"""
import asyncio
import sys
from services.email_matcher import get_email_matcher

async def test_matcher():
    print("Test EmailMatcher...")

    matcher = get_email_matcher()
    print(f"Matcher instance créée: {matcher}")

    # Charger les données SAP
    print("\nChargement des données SAP...")
    try:
        await matcher.ensure_cache()
        print(f"✅ Clients chargés: {len(matcher._clients_cache)}")
        print(f"✅ Produits chargés: {len(matcher._items_cache)}")
        print(f"✅ Domaines indexés: {len(matcher._client_domains)}")

        # Afficher quelques clients pour debug
        if matcher._clients_cache:
            print("\nPremiers clients:")
            for client in matcher._clients_cache[:5]:
                print(f"  - {client.get('CardName')} ({client.get('CardCode')}) - {client.get('EmailAddress', 'N/A')}")

        # Tester avec l'email SAVERGLASS
        print("\n" + "="*60)
        print("Test avec email SAVERGLASS")
        print("="*60)

        email_body = """
        De : Quesnel, Christophe <chq@saverglass.com>
        Objet : demande de prix

        Bonjour Manu
        Pourrais-tu me faire un devis pour l'article suivant
        2323060165 qté : 1
        Merci
        --
        Christophe QUESNEL
        MAGASINIER I.S.
        Atelier I.S. Mécaniciens SGL
        +33344464269
        """

        result = await matcher.match_email(
            body=email_body,
            sender_email="chq@saverglass.com",
            subject="demande de prix"
        )

        print(f"\n✅ Domaines extraits: {result.extracted_domains}")
        print(f"✅ Clients matchés: {len(result.clients)}")

        if result.clients:
            for client in result.clients:
                print(f"  - {client.card_name} ({client.card_code})")
                print(f"    Email: {client.email_address}")
                print(f"    Score: {client.score}")
                print(f"    Raison: {client.match_reason}")

        if result.best_client:
            print(f"\n🎯 MEILLEUR CLIENT:")
            print(f"   CardCode: {result.best_client.card_code}")
            print(f"   CardName: {result.best_client.card_name}")
            print(f"   Score: {result.best_client.score}")
        else:
            print("\n❌ Aucun client matché!")

        print(f"\n✅ Produits matchés: {len(result.products)}")
        for product in result.products:
            print(f"  - {product.item_code}: {product.item_name} (qté: {product.quantity})")

        # TEST MARMARACAM
        print("\n" + "="*60)
        print("Test avec email MarmaraCam")
        print("="*60)

        test_cases = [
            ("Demande chiffrage MARMARA CAM", "avec espace (MARMARA CAM)"),
            ("Demande chiffrage MarmaraCam", "sans espace (MarmaraCam)"),
            ("Demande chiffrage pour Marmara Cam", "espace + casse mixte"),
            ("Client : marmaracam", "minuscule sans espace"),
        ]

        for body, description in test_cases:
            print(f"\n📧 Test: {description}")
            print(f"   Texte: '{body}'")

            result = await matcher.match_email(
                body=body,
                sender_email="test@example.com",
                subject=""
            )

            if result.best_client:
                print(f"   ✅ Match trouvé: {result.best_client.card_name} ({result.best_client.card_code})")
                print(f"      Score: {result.best_client.score}")
                print(f"      Raison: {result.best_client.match_reason}")
            else:
                print(f"   ❌ Aucun match trouvé")

    except Exception as e:
        print(f"❌ ERREUR: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

if __name__ == "__main__":
    success = asyncio.run(test_matcher())
    sys.exit(0 if success else 1)
