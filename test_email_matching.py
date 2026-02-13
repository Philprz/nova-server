"""Test du matching intelligent pour les emails problématiques"""
import asyncio
import sys
from services.email_matcher import EmailMatcher

async def test_matching():
    """Test des cas problématiques"""

    matcher = EmailMatcher()

    # Charger le cache SAP
    print("Chargement cache SAP...")
    await matcher.ensure_cache()
    print(f"Cache chargé: {len(matcher._clients_cache)} clients, {len(matcher._items_cache)} produits\n")

    # Test 1: Email MarmaraCam
    print("="*60)
    print("TEST 1: EMAIL MARMARACAM")
    print("="*60)

    email_1 = {
        "subject": "Demande chiffrage MarmaraCam",
        "from": "msezen@marmaracam.com.tr",
        "body": """
        Veuillez trouver ci-joint la demande de chiffrage pour des éléments Sheppee international.
        Please send the offer to the fax number or email adress below !
        Fax:+90282675102
        """,
        "text": "Demande chiffrage MarmaraCam Veuillez trouver ci-joint la demande de chiffrage pour des éléments Sheppee international. Please send the offer to the fax number or email adress below ! Fax:+90282675102"
    }

    print(f"\nSubject: {email_1['subject']}")
    print(f"From: {email_1['from']}")

    # Détection mots-clés devis
    text_lower = email_1["text"].lower()
    keywords = ['devis', 'quote', 'quotation', 'chiffrage', 'prix', 'price', 'demande']
    found_keywords = [kw for kw in keywords if kw in text_lower]
    print(f"\nMots-cles detectes: {found_keywords}")

    # Matching client
    client_matches = await matcher._match_clients(email_1["from"], email_1["text"])
    print(f"\nClients matches: {len(client_matches)}")
    for match in client_matches[:5]:
        print(f"   - {match.card_code}: {match.card_name}")
        print(f"     Score: {match.score}, Raison: {match.match_reason}")

    # Test 2: Email SAVERGLASS
    print("\n" + "="*60)
    print("TEST 2: EMAIL SAVERGLASS")
    print("="*60)

    email_2 = {
        "subject": "demande de prix",
        "from": "chq@saverglass.com",
        "body": """
        Bonjour Manu
        Pourrais-tu me faire un devis pour l'article suivant 2323060165 qté : 1
        Merci -- Christophe QUESNEL MAGASINIER
        """,
        "text": "demande de prix Bonjour Manu Pourrais-tu me faire un devis pour l'article suivant 2323060165 qté : 1 Merci -- Christophe QUESNEL MAGASINIER"
    }

    print(f"\n Subject: {email_2['subject']}")
    print(f" From: {email_2['from']}")

    # Détection mots-clés devis
    text_lower = email_2["text"].lower()
    keywords = ['devis', 'quote', 'quotation', 'chiffrage', 'prix', 'price', 'demande']
    found_keywords = [kw for kw in keywords if kw in text_lower]
    print(f"\n Mots-clés détectés: {found_keywords}")

    # Matching client
    client_matches = await matcher._match_clients(email_2["from"], email_2["text"])
    print(f"\n Clients matchés: {len(client_matches)}")
    for match in client_matches[:5]:
        print(f"   - {match.card_code}: {match.card_name}")
        print(f"     Score: {match.score}, Raison: {match.match_reason}")

    # Test 3: Recherche produit SAVERGLASS
    print("\n" + "="*60)
    print("TEST 3: MATCHING PRODUIT 2323060165")
    print("="*60)

    product_matches = await matcher._match_single_product_intelligent(
        email_text=email_2["text"],
        supplier_card_code=client_matches[0].card_code if client_matches else None
    )

    print(f"\n Produits matchés: {len(product_matches)}")
    for match in product_matches[:5]:
        print(f"   - {match.item_code}: {match.item_name}")
        print(f"     Score: {match.score}, Raison: {match.match_reason}")
        if match.not_found_in_sap:
            print(f"     ALERTE PENDING - Non trouvé dans SAP")

if __name__ == "__main__":
    asyncio.run(test_matching())
