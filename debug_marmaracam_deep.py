"""Debug profond - Voir EXACTEMENT ce qui se passe"""
import asyncio
from services.email_matcher import get_email_matcher
from services.email_analyzer import get_email_analyzer

async def debug_deep():
    """Debug complet avec tous les détails"""

    # Texte réel de l'email MarmaraCam
    subject = "Demande chiffrage MarmaraCam"
    sender_email = "devis@rondot-poc.itspirit.ovh"

    # Body simplifié pour le test
    body = """from: msezen@marmaracam.com.tr

Veuillez trouver ci-joint la demande de chiffrage pour des éléments Sheppee international.

Please send the offer to the fax number or email adress below!"""

    print("=" * 80)
    print("DEBUG PROFOND - MARMARACAM")
    print("=" * 80)
    print(f"Subject: {subject}")
    print(f"Sender: {sender_email}")
    print(f"Body preview: {body[:100]}...")
    print()

    # === ÉTAPE 1: Vérifier l'extraction des domaines ===
    print("=" * 80)
    print("ÉTAPE 1: EXTRACTION DES DOMAINES")
    print("=" * 80)

    matcher = get_email_matcher()
    await matcher.ensure_cache()

    # Extraire les domaines (méthode privée mais on peut l'appeler pour debug)
    analyzer = get_email_analyzer()
    clean_body = analyzer._clean_html(body)
    full_text = f"{subject} {clean_body}"

    extracted_domains = matcher._extract_email_domains(full_text, sender_email)

    print(f"Domaines extraits: {extracted_domains}")
    print()

    if not extracted_domains:
        print("[PROBLEME] Aucun domaine extrait!")
        print("Raison probable:")
        print("  - Le domaine de l'expéditeur est ignoré (interne)")
        print("  - Les domaines dans le texte ne sont pas détectés")
        print()
    else:
        print(f"[OK] {len(extracted_domains)} domaine(s) extrait(s)")
        for domain in extracted_domains:
            print(f"  - {domain}")
        print()

    # === ÉTAPE 2: Tester le matching manuellement ===
    print("=" * 80)
    print("ÉTAPE 2: TEST MATCHING MARMARA CAM")
    print("=" * 80)

    # Simuler le matching pour MarmaraCam
    card_code = "C0249"
    card_name = "MARMARA CAM SANAYI VE TICARET AS"

    print(f"Client test: {card_code} - {card_name}")
    print()

    # Normaliser le nom
    name_normalized = matcher._normalize(card_name)
    name_parts = name_normalized.split()

    print(f"Nom normalisé: '{name_normalized}'")
    print(f"Parties: {name_parts}")
    print()

    # Tester toutes les combinaisons
    print("Test des combinaisons de mots:")
    for num_words in range(1, min(4, len(name_parts) + 1)):
        compact_name = ''.join(name_parts[:num_words])
        print(f"  {num_words} mot(s): '{compact_name}'")

        for domain in extracted_domains:
            domain_base = domain.split('.')[0]
            if compact_name == domain_base:
                print(f"    -> MATCH EXACT avec {domain}! Score devrait etre 97")
            else:
                # Fuzzy
                from difflib import SequenceMatcher
                ratio = SequenceMatcher(None, domain_base, compact_name).ratio()
                print(f"    -> Fuzzy avec {domain}: {ratio:.0%}")

    print()

    # === ÉTAPE 3: Tester le matching pour SHEPPEE ===
    print("=" * 80)
    print("ÉTAPE 3: TEST MATCHING SHEPPEE (concurrent)")
    print("=" * 80)

    sheppee_name = "SHEPPEE"
    text_normalized = matcher._normalize(full_text)

    print(f"Client concurrent: SHEPPEE")
    print(f"Texte normalisé (100 premiers chars): {text_normalized[:100]}...")
    print()

    # Vérifier si SHEPPEE est dans le texte
    if "sheppee" in text_normalized:
        print("[PROBLEME] 'sheppee' trouvé dans le texte!")
        print("  → SHEPPEE aura score 90 (Stratégie 2: Nom exact dans texte)")
        print()

    # === ÉTAPE 4: Appeler le matching réel ===
    print("=" * 80)
    print("ÉTAPE 4: MATCHING RÉEL")
    print("=" * 80)

    match_result = await matcher.match_email(
        body=clean_body,
        sender_email=sender_email,
        subject=subject
    )

    print(f"Clients matchés: {len(match_result.clients)}")
    print()

    for i, client in enumerate(match_result.clients[:5], 1):
        marker = "← GAGNANT" if i == 1 else ""
        is_marmara = "marmara" in client.card_name.lower()
        print(f"{i}. {client.card_code}: {client.card_name}")
        print(f"   Score: {client.score}")
        print(f"   Raison: {client.match_reason} {marker}")
        if is_marmara and i != 1:
            print(f"   [WARNING] MarmaraCam devrait etre #1!")
        print()

    print("=" * 80)
    print("DIAGNOSTIC")
    print("=" * 80)

    marmara_found = False
    marmara_position = None
    marmara_score = None

    for i, client in enumerate(match_result.clients, 1):
        if "marmara" in client.card_name.lower():
            marmara_found = True
            marmara_position = i
            marmara_score = client.score
            break

    if not marmara_found:
        print("[ERREUR CRITIQUE] MarmaraCam n'est PAS dans les résultats!")
    elif marmara_position == 1:
        print("[OK] MarmaraCam est #1")
    else:
        print(f"[PROBLEME] MarmaraCam est #{marmara_position} avec score {marmara_score}")
        winner = match_result.clients[0]
        print(f"Le gagnant est: {winner.card_name} (score {winner.score})")
        print()
        print("RAISONS POSSIBLES:")
        if winner.score > marmara_score:
            print(f"  1. Score concurrent ({winner.score}) > MarmaraCam ({marmara_score})")
            print(f"  2. La Stratégie 1b (domaine match) ne s'est pas déclenchée")
            print(f"     → Domaines extraits: {extracted_domains}")
            print(f"     → Vérifier que 'marmaracam' match bien un domaine")

if __name__ == "__main__":
    asyncio.run(debug_deep())
