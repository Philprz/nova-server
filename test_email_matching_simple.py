"""Test simple du matching intelligent"""
import asyncio
from services.email_matcher import EmailMatcher

async def test():
    matcher = EmailMatcher()
    print("Chargement cache SAP...")
    await matcher.ensure_cache()
    print(f"Cache: {len(matcher._clients_cache)} clients, {len(matcher._items_cache)} produits\n")

    # Test 1: MarmaraCam
    print("="*60)
    print("TEST 1: MARMARACAM")
    print("="*60)

    email_text = "Demande chiffrage MarmaraCam Veuillez trouver ci-joint la demande de chiffrage pour des elements Sheppee international"
    email_from = "msezen@marmaracam.com.tr"

    print(f"Email: {email_from}")
    print(f"Texte: {email_text[:80]}...")

    # Matching clients
    clients = matcher._match_clients(email_from, email_text)
    print(f"\nClients trouves: {len(clients)}")
    for c in clients[:3]:
        print(f"  - {c.card_code}: {c.card_name}")
        print(f"    Score: {c.score}, Raison: {c.match_reason}")

    # Test 2: SAVERGLASS
    print("\n" + "="*60)
    print("TEST 2: SAVERGLASS")
    print("="*60)

    email_text = "demande de prix Bonjour Manu Pourrais-tu me faire un devis pour l'article suivant 2323060165 qte : 1"
    email_from = "chq@saverglass.com"

    print(f"Email: {email_from}")
    print(f"Texte: {email_text[:80]}...")

    # Matching clients
    clients = matcher._match_clients(email_from, email_text)
    print(f"\nClients trouves: {len(clients)}")
    for c in clients[:3]:
        print(f"  - {c.card_code}: {c.card_name}")
        print(f"    Score: {c.score}, Raison: {c.match_reason}")

    # Test produit
    print("\n--- Matching produit 2323060165 ---")
    product = await matcher._match_single_product_intelligent(
        code="2323060165",
        description="",
        text=email_text,
        supplier_card_code=clients[0].card_code if clients else None
    )

    if product:
        print(f"Produit trouve: {product.item_code}: {product.item_name}")
        print(f"Score: {product.score}, Raison: {product.match_reason}")
        if product.not_found_in_sap:
            print("ALERTE: PENDING - Non trouve dans SAP")
    else:
        print("Aucun produit trouve")

if __name__ == "__main__":
    asyncio.run(test())
