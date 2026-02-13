"""Debug: Récupérer l'email MarmaraCam RÉEL via l'API et analyser exactement ce que le système voit"""
import requests
import json
import asyncio
from services.email_analyzer import get_email_analyzer

# INSTRUCTIONS:
# 1. Trouver l'ID de l'email "Demande chiffrage MarmaraCam"
# 2. Remplacer EMAIL_ID ci-dessous
EMAIL_ID = "REMPLACER_PAR_ID_EMAIL_MARMARACAM"

async def debug_real_email():
    """
    Récupère l'email RÉEL via l'API et analyse exactement ce que le système voit.
    """

    if EMAIL_ID == "REMPLACER_PAR_ID_EMAIL_MARMARACAM":
        print("=" * 80)
        print("ERREUR: Vous devez remplacer EMAIL_ID par l'ID reel")
        print("=" * 80)
        print()
        print("Pour trouver l'ID de l'email MarmaraCam:")
        print()
        print("1. Ouvrir l'interface web: http://localhost:5173")
        print("2. Trouver l'email 'Demande chiffrage MarmaraCam'")
        print("3. Ouvrir DevTools (F12) > Network")
        print("4. Cliquer sur l'email")
        print("5. Chercher la requête: /api/graph/emails/{id}/analyze")
        print("6. Copier l'{id} de l'URL")
        print()
        print("OU via curl:")
        print('  curl http://localhost:8000/api/graph/emails | jq \'.[] | select(.subject | contains("MarmaraCam")) | .id\'')
        return

    print("=" * 80)
    print("DEBUG EMAIL MARMARACAM REEL - VIA API")
    print("=" * 80)
    print(f"Email ID: {EMAIL_ID}")
    print()

    # === ÉTAPE 1: Récupérer les métadonnées de l'email ===
    print("--- ETAPE 1: Recuperer les metadonnees de l'email ---")
    try:
        r = requests.get(f"http://localhost:8000/api/graph/emails/{EMAIL_ID}")
        r.raise_for_status()
        email_meta = r.json()

        print(f"Sujet: {email_meta.get('subject', 'N/A')}")
        print(f"From: {email_meta.get('from_name', 'N/A')} <{email_meta.get('from_address', 'N/A')}>")
        print(f"Body preview (interface): {email_meta.get('body_preview', 'N/A')[:200]}...")
        print(f"Body content disponible: {email_meta.get('body_content') is not None}")
        print(f"Attachments: {email_meta.get('attachment_count', 0)} piece(s)")
        print()

    except Exception as e:
        print(f"[ERREUR] Impossible de recuperer l'email: {e}")
        print("Verifiez:")
        print("  1. Le backend est lance: python main.py")
        print("  2. L'EMAIL_ID est correct")
        print("  3. Le service Microsoft Graph est configure")
        return

    # === ÉTAPE 2: Récupérer le BODY complet ===
    print("--- ETAPE 2: Recuperer le BODY COMPLET ---")
    try:
        r = requests.get(f"http://localhost:8000/api/graph/emails/{EMAIL_ID}/body")
        r.raise_for_status()
        body_data = r.json()

        body_text = body_data.get('body', '')
        body_type = body_data.get('type', 'text')

        print(f"Type: {body_type}")
        print(f"Longueur: {len(body_text)} caracteres")
        print(f"Contenu (300 premiers caracteres):")
        print("-" * 80)
        print(body_text[:300])
        print("-" * 80)
        print()

    except Exception as e:
        print(f"[WARNING] Impossible de recuperer le body complet: {e}")
        print("Utilisation du body_preview a la place")
        body_text = email_meta.get('body_preview', '')
        body_type = 'text'

    # === ÉTAPE 3: Nettoyer le HTML (comme le fait le système) ===
    print("--- ETAPE 3: Nettoyage HTML (comme le systeme) ---")
    analyzer = get_email_analyzer()
    clean_text = analyzer._clean_html(body_text)

    print(f"Texte nettoye (300 premiers caracteres):")
    print("-" * 80)
    print(clean_text[:300])
    print("-" * 80)
    print()

    # === ÉTAPE 4: Vérifier la présence de "chiffrage" ===
    print("--- ETAPE 4: Verification presence 'chiffrage' ---")
    subject = email_meta.get('subject', '')
    subject_lower = subject.lower()
    clean_lower = clean_text.lower()

    print(f"'chiffrage' dans sujet: {'OUI' if 'chiffrage' in subject_lower else 'NON'}")
    print(f"'demande de chiffrage' dans body nettoye: {'OUI' if 'demande de chiffrage' in clean_lower else 'NON'}")
    print(f"'chiffrage' dans body nettoye: {'OUI' if 'chiffrage' in clean_lower else 'NON'}")
    print()

    if 'chiffrage' not in clean_lower and 'chiffrage' not in subject_lower:
        print("[ALERTE] Le mot 'chiffrage' n'est PAS present dans le texte analyse!")
        print("Cela explique pourquoi l'email n'est pas detecte.")
        print()
        print("Verification du body_preview:")
        preview = email_meta.get('body_preview', '')
        print(f"Preview: {preview}")
        print(f"'chiffrage' dans preview: {'OUI' if 'chiffrage' in preview.lower() else 'NON'}")

    # === ÉTAPE 5: Test du pré-filtrage avec le texte RÉEL ===
    print("--- ETAPE 5: Test pre-filtrage avec texte REEL ---")
    quick_result = analyzer.quick_classify(subject, clean_text)

    print(f"Score: {quick_result['score']}")
    print(f"Likely quote: {quick_result['likely_quote']}")
    print(f"Confidence: {quick_result['confidence']}")
    print(f"Regles matchees:")
    for rule in quick_result['matched_rules']:
        print(f"  [+] {rule}")
    print()

    if not quick_result['likely_quote']:
        print("[PROBLEME TROUVE] Pre-filtrage classe comme NON PERTINENT")
        print(f"Score {quick_result['score']} < 15")
        print()
        print("RAISON:")
        if not quick_result['matched_rules']:
            print("  Aucune regle matchee!")
        print()
        print("DEBUG - Texte analyse:")
        print(f"  Sujet: '{subject}'")
        print(f"  Body (100 premiers car): '{clean_text[:100]}'")

    # === ÉTAPE 6: Appeler l'API /analyze avec force=true ===
    print("--- ETAPE 6: Appel API /analyze avec force=true ---")
    try:
        r = requests.post(
            f"http://localhost:8000/api/graph/emails/{EMAIL_ID}/analyze?force=true"
        )
        r.raise_for_status()
        analysis = r.json()

        print(f"Classification: {analysis.get('classification', 'N/A')}")
        print(f"Is quote request: {analysis.get('is_quote_request', 'N/A')}")
        print(f"Confidence: {analysis.get('confidence', 'N/A')}")
        print(f"Quick filter passed: {analysis.get('quick_filter_passed', 'N/A')}")
        print(f"Reasoning: {analysis.get('reasoning', 'N/A')[:200]}...")
        print()

        if not analysis.get('is_quote_request', False):
            print("[CONFIRMATION] L'API classifie aussi comme NON PERTINENT")
            print()
            print("=== REPONSE COMPLETE API ===")
            print(json.dumps(analysis, indent=2, ensure_ascii=False))

    except Exception as e:
        print(f"[ERREUR] Appel API echoue: {e}")

    print()
    print("=" * 80)
    print("DIAGNOSTIC FINAL")
    print("=" * 80)

    if quick_result['likely_quote']:
        print("[OK] Le systeme DEVRAIT detecter cet email comme DEVIS")
        print("Si l'interface montre 'Non pertinent', c'est un probleme de CACHE")
        print()
        print("SOLUTION:")
        print("  1. Rafraichir la page (F5)")
        print("  2. Ou cliquer sur 'Reanalyser' si disponible")
    else:
        print("[PROBLEME] Le systeme classe comme NON PERTINENT")
        print()
        print("CAUSE PROBABLE:")
        if 'chiffrage' not in clean_lower and 'chiffrage' not in subject_lower:
            print("  -> Le mot 'chiffrage' est ABSENT du texte analyse")
            print("  -> Le body_preview est peut-etre TRONQUE")
            print()
            print("SOLUTION:")
            print("  Modifier routes_graph.py ligne 405:")
            print("  Au lieu de: body_text = email.body_content or email.body_preview")
            print("  Utiliser:   body_text = await get_full_body(email_id)")
        else:
            print("  -> Autre raison (verifier les logs ci-dessus)")

if __name__ == "__main__":
    asyncio.run(debug_real_email())
