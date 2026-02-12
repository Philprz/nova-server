"""
Test du flux complet d'analyse : EmailAnalyzer + EmailMatcher (comme routes_graph.py)
"""
import asyncio
from services.email_analyzer import get_email_analyzer, ExtractedQuoteData, ExtractedProduct
from services.email_matcher import get_email_matcher

async def test_full_analysis():
    analyzer = get_email_analyzer()
    matcher = get_email_matcher()

    # Charger le cache SAP
    print("Chargement cache SAP...")
    await matcher.ensure_cache()
    print(f"  Clients: {len(matcher._clients_cache)}")
    print(f"  Produits: {len(matcher._items_cache)}\n")

    test_cases = [
        {
            "subject": "Demande chiffrage MarmaraCam",
            "body": "Bonjour, pouvez-vous me faire un devis pour MarmaraCam? Merci",
            "sender": "test@example.com",
            "description": "MarmaraCam sans espace"
        },
        {
            "subject": "Demande de prix",
            "body": "De : Quesnel, Christophe <chq@saverglass.com>\nBonjour Manu\nPourrais-tu me faire un devis pour l'article suivant\n2323060165 qte : 1\nMerci",
            "sender": "chq@saverglass.com",
            "description": "SAVERGLASS avec email domaine"
        },
        {
            "subject": "Devis MARMARA CAM",
            "body": "Demande de devis pour le client MARMARA CAM",
            "sender": "test@example.com",
            "description": "MARMARA CAM avec espace"
        }
    ]

    print("="*70)
    print("TESTS ANALYSE COMPLETE (Analyzer + Matcher)")
    print("="*70)

    for i, test in enumerate(test_cases, 1):
        print(f"\n{i}. {test['description']}")
        print(f"   Sujet: {test['subject']}")
        print(f"   De: {test['sender']}")

        # Etape 1: Analyse LLM/rules
        result = await analyzer.analyze_email(
            subject=test['subject'],
            body=test['body'],
            sender_email=test['sender']
        )

        print(f"   Classification: {result.classification}")
        print(f"   Is quote request: {result.is_quote_request}")

        # Etape 2: Enrichissement SAP (comme routes_graph.py ligne 414-460)
        clean_text = analyzer._clean_html(test['body'])
        match_result = await matcher.match_email(
            body=clean_text,
            sender_email=test['sender'],
            subject=test['subject']
        )

        # Enrichir extracted_data avec les matchs SAP
        if match_result.best_client or match_result.products:
            if result.extracted_data is None:
                result.extracted_data = ExtractedQuoteData()

            # Client matche
            if match_result.best_client:
                result.extracted_data.client_name = match_result.best_client.card_name
                result.extracted_data.client_card_code = match_result.best_client.card_code
                if match_result.best_client.email_address:
                    result.extracted_data.client_email = match_result.best_client.email_address

            # Produits matches
            if match_result.products:
                result.extracted_data.products = [
                    ExtractedProduct(
                        description=f"{p.item_name}" if p.item_name else f"Article {p.item_code}",
                        quantity=p.quantity,
                        unit="pcs",
                        reference=p.item_code
                    )
                    for p in match_result.products
                ]

            # Marquer comme devis si produits trouves
            if match_result.products and not result.is_quote_request:
                result.is_quote_request = True
                result.classification = "QUOTE_REQUEST"

        # Afficher les resultats enrichis
        if result.extracted_data:
            if result.extracted_data.client_card_code:
                print(f"   >> CLIENT MATCHE: {result.extracted_data.client_name} ({result.extracted_data.client_card_code})")
            else:
                print(f"   >> Client detecte (LLM): {result.extracted_data.client_name or 'NON DETECTE'}")

            if result.extracted_data.products:
                print(f"   >> PRODUITS MATCHES: {len(result.extracted_data.products)}")
                for p in result.extracted_data.products:
                    print(f"      - {p.reference}: {p.description} (qte: {p.quantity})")
            else:
                print(f"   >> Produits: AUCUN")
        else:
            print(f"   >> Extracted data: NONE")

    print("\n" + "="*70)

if __name__ == "__main__":
    asyncio.run(test_full_analysis())
