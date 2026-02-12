"""
Test de l'analyse d'emails pour les demandes de devis
"""
import asyncio
from services.email_analyzer import EmailAnalyzer

async def test_analysis():
    analyzer = EmailAnalyzer()

    test_cases = [
        "Demande chiffrage MarmaraCam",
        "Demande de prix concernant SAVERGLASS",
        "Demande de devis pour client SAVERGLASS",
        "Pouvez-vous me faire un devis pour MarmaraCam"
    ]

    print("=== Test analyse emails ===\n")

    for i, text in enumerate(test_cases, 1):
        print(f"{i}. Test: '{text}'")

        try:
            result = await analyzer.analyze_email(
                subject=text,
                body=text,
                sender_email="test@example.com"
            )

            print(f"   Classification: {result.classification}")
            print(f"   Is quote request: {result.is_quote_request}")
            print(f"   Confidence: {result.confidence}")
            if result.extracted_data:
                print(f"   Client: {result.extracted_data.client_name or 'NON DETECTE'}")
                print(f"   Produits: {len(result.extracted_data.products)} produit(s)")
            else:
                print(f"   Extracted data: NONE")
            print()

        except Exception as e:
            print(f"   ERREUR: {e}\n")

if __name__ == "__main__":
    asyncio.run(test_analysis())
