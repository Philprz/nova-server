"""Test de détection de l'email 'Demande chiffrage MarmaraCam'"""
import asyncio
from services.email_analyzer import get_email_analyzer

async def test_chiffrage_detection():
    """Vérifie que 'Demande chiffrage MarmaraCam' est bien détecté comme devis"""

    # Email problématique signalé
    subject = "Demande chiffrage MarmaraCam"
    body = """Bonjour,

Veuillez trouver ci-joint la demande de chiffrage pour le projet MarmaraCam.

Pouvez-vous nous faire un chiffrage rapide ?

Merci d'avance,
Client"""

    from_address = "client@example.com"

    print("=" * 70)
    print("TEST DÉTECTION 'DEMANDE CHIFFRAGE' - FIX FAUX NÉGATIF")
    print("=" * 70)
    print(f"Sujet: {subject}")
    print(f"Corps (extrait): {body[:100]}...")
    print()

    analyzer = get_email_analyzer()

    # 1. Test du pré-filtrage rapide (quick_classify)
    print("--- Étape 1: Pré-filtrage (règles sans LLM) ---")
    quick_result = analyzer.quick_classify(subject, body)
    print(f"Score total: {quick_result['score']}")
    print(f"Likely quote: {quick_result['likely_quote']}")
    print(f"Confidence: {quick_result['confidence']}")
    print(f"Regles matchees:")
    for rule in quick_result['matched_rules']:
        print(f"  [+] {rule}")
    print()

    # Verification du resultat
    if quick_result['likely_quote']:
        print("[OK] PRE-FILTRAGE: Email correctement classe comme 'demande de devis'")
    else:
        print("[ERREUR] PRE-FILTRAGE: Email classe comme 'Non pertinent' (FAUX NEGATIF)")
    print()

    # 2. Test de l'analyse complète avec LLM
    print("--- Étape 2: Analyse complète (avec LLM) ---")
    try:
        analysis = await analyzer.analyze_email(
            subject=subject,
            body=body,
            sender_email=from_address,
            sender_name="Test Client",
            pdf_contents=[]
        )

        print(f"Classification: {analysis.classification}")
        print(f"Is quote request: {analysis.is_quote_request}")
        print(f"Confidence: {analysis.confidence}")
        print(f"Reasoning: {analysis.reasoning}")
        print()

        if analysis.is_quote_request:
            print("[OK] ANALYSE LLM: Email correctement classe comme 'QUOTE_REQUEST'")
            if analysis.extracted_data:
                print(f"   Client extrait: {analysis.extracted_data.client_name}")
                print(f"   Produits: {len(analysis.extracted_data.products)}")
        else:
            print("[ERREUR] ANALYSE LLM: Email classe comme 'NON PERTINENT' (FAUX NEGATIF)")

    except Exception as e:
        print(f"[WARNING] ANALYSE LLM: Echec ({type(e).__name__}: {e})")
        print("   -> Fallback sur pre-filtrage uniquement")

    print()
    print("=" * 70)
    print("RESUME:")
    print("  - Pre-filtrage (regles): " + ("[OK] DETECTE" if quick_result['likely_quote'] else "[ERREUR] NON DETECTE"))
    print("  - Score pre-filtrage: " + str(quick_result['score']) + " (seuil: 15)")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(test_chiffrage_detection())
