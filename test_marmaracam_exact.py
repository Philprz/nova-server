"""Test avec le texte EXACT de l'email MarmaraCam problématique"""
import asyncio
from services.email_analyzer import get_email_analyzer

async def test_marmaracam_exact():
    """
    Test avec les données EXACTES de l'email MarmaraCam.
    """

    # Données EXACTES de l'email problématique
    subject = "Demande chiffrage MarmaraCam"

    # Corps exact tel que visible dans l'interface
    body = """Veuillez trouver ci-joint la demande de chiffrage pour des éléments Sheppee international. Please send the offer to...

De : Philippe PEREZ
Transféré de : msezen@marmaracam.com.tr"""

    sender_email = "devis@rondot-poc.itspirit.ovh"  # Email de transfert
    sender_name = "Philippe PEREZ"

    print("=" * 80)
    print("TEST EMAIL MARMARACAM - TEXTE EXACT")
    print("=" * 80)
    print(f"Sujet: {subject}")
    print(f"Expediteur: {sender_name} <{sender_email}>")
    print(f"Corps (preview):")
    print("-" * 80)
    print(body)
    print("-" * 80)
    print()

    analyzer = get_email_analyzer()

    # === TEST 1: PRÉ-FILTRAGE (RÈGLES) ===
    print("=" * 80)
    print("TEST 1: PRÉ-FILTRAGE (règles sans LLM)")
    print("=" * 80)

    quick_result = analyzer.quick_classify(subject, body)

    print(f"Score total: {quick_result['score']}")
    print(f"Likely quote: {quick_result['likely_quote']}")
    print(f"Confidence: {quick_result['confidence']}")
    print(f"Regles matchees:")
    for rule in quick_result['matched_rules']:
        print(f"  [+] {rule}")
    print()

    # Diagnostic détaillé
    print("--- DIAGNOSTIC DÉTAILLÉ ---")

    # Vérifier les mots-clés dans le sujet
    from services.email_analyzer import QUOTE_KEYWORDS_SUBJECT, QUOTE_KEYWORDS_BODY
    subject_lower = subject.lower()
    body_lower = body.lower()

    print("\n1. Mots-clés SUJET:")
    found_in_subject = []
    for keyword in QUOTE_KEYWORDS_SUBJECT:
        if keyword in subject_lower:
            found_in_subject.append(keyword)
            print(f"   [MATCH] '{keyword}' trouvé dans sujet")

    if not found_in_subject:
        print("   [WARNING] Aucun mot-clé trouvé dans le sujet!")

    print("\n2. Phrases CORPS:")
    found_in_body = []
    for phrase in QUOTE_KEYWORDS_BODY:
        if phrase in body_lower:
            found_in_body.append(phrase)
            print(f"   [MATCH] '{phrase}' trouvé dans corps")

    if not found_in_body:
        print("   [WARNING] Aucune phrase trouvée dans le corps!")
        print(f"\n   Mots-clés recherchés dans le corps:")
        for phrase in QUOTE_KEYWORDS_BODY:
            print(f"     - '{phrase}'")
        print(f"\n   Corps converti en minuscules:")
        print(f"     '{body_lower}'")

    print("\n3. Patterns de quantité:")
    from services.email_analyzer import QUANTITY_PATTERNS
    import re
    combined = f"{subject_lower} {body_lower}"
    found_patterns = []
    for pattern in QUANTITY_PATTERNS:
        if re.search(pattern, combined, re.IGNORECASE):
            found_patterns.append(pattern)
            print(f"   [MATCH] Pattern trouvé: {pattern}")

    if not found_patterns:
        print("   [INFO] Aucun pattern de quantité trouvé (normal si pas de quantité dans l'email)")

    print("\n--- RESULTAT PRE-FILTRAGE ---")
    if quick_result['likely_quote']:
        print(f"[OK] Score {quick_result['score']} >= 15 -> Classe comme DEVIS")
    else:
        print(f"[ERREUR] Score {quick_result['score']} < 15 -> Classe comme NON PERTINENT")
        print("\nPOURQUOI?")
        if not found_in_subject:
            print("  -> Aucun mot-cle trouve dans le SUJET (attendu: +30 pts)")
        if not found_in_body:
            print("  -> Aucune phrase trouvee dans le CORPS (attendu: +25 pts)")

    print()

    # === TEST 2: ANALYSE COMPLÈTE LLM ===
    print("=" * 80)
    print("TEST 2: ANALYSE COMPLÈTE (avec LLM)")
    print("=" * 80)

    try:
        analysis = await analyzer.analyze_email(
            subject=subject,
            body=body,
            sender_email=sender_email,
            sender_name=sender_name,
            pdf_contents=[]
        )

        print(f"Classification: {analysis.classification}")
        print(f"Is quote request: {analysis.is_quote_request}")
        print(f"Confidence: {analysis.confidence}")
        print(f"Quick filter passed: {analysis.quick_filter_passed}")
        print(f"Reasoning: {analysis.reasoning}")
        print()

        if analysis.extracted_data:
            print("Données extraites:")
            print(f"  - Client: {analysis.extracted_data.client_name}")
            print(f"  - Email: {analysis.extracted_data.client_email}")
            print(f"  - Produits: {len(analysis.extracted_data.products)}")
            for p in analysis.extracted_data.products:
                print(f"    * {p.description} (qté: {p.quantity}, ref: {p.reference})")

        print("\n--- RESULTAT ANALYSE LLM ---")
        if analysis.is_quote_request:
            print("[OK] LLM classifie comme QUOTE_REQUEST")
        else:
            print("[ERREUR] LLM classifie comme NON PERTINENT")
            print(f"Classification: {analysis.classification}")

    except Exception as e:
        print(f"[ERREUR] Analyse LLM échouée: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

    print()
    print("=" * 80)
    print("RESUME FINAL")
    print("=" * 80)
    print(f"Pre-filtrage: {'[OK] DEVIS' if quick_result['likely_quote'] else '[ERREUR] NON PERTINENT'} (score={quick_result['score']})")

    # Hypotheses de diagnostic
    print("\nHYPOTHESES POSSIBLES:")
    print("1. Body tronque? -> Verifier que body_preview contient 'demande de chiffrage'")
    print("2. HTML mal nettoye? -> Verifier _clean_html() avec le HTML reel")
    print("3. Cache? -> Verifier avec force=true dans l'API")
    print("4. Format transfere? -> Verifier si 'De : Philippe PEREZ' interfere")

if __name__ == "__main__":
    asyncio.run(test_marmaracam_exact())
