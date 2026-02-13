"""Test de l'API d'analyse avec un vrai email contenant 'chiffrage'"""
import requests
import json

# IMPORTANT: Remplacer cet ID par l'ID réel de l'email "Demande chiffrage MarmaraCam"
EMAIL_ID = "REMPLACER_PAR_VOTRE_EMAIL_ID"

def test_api_chiffrage():
    """
    Test direct de l'API /analyze avec force=true pour bypasser le cache.

    Instructions:
    1. Trouver l'ID de l'email "Demande chiffrage MarmaraCam" via:
       GET http://localhost:8001/api/graph/emails

    2. Remplacer EMAIL_ID ci-dessus avec l'ID réel

    3. Lancer ce script
    """

    if EMAIL_ID == "REMPLACER_PAR_VOTRE_EMAIL_ID":
        print("=" * 70)
        print("ERREUR: Vous devez d'abord remplacer EMAIL_ID par l'ID reel")
        print("=" * 70)
        print()
        print("Etape 1: Recuperer la liste des emails")
        print("  GET http://localhost:8001/api/graph/emails")
        print()
        print("Etape 2: Trouver l'email 'Demande chiffrage MarmaraCam' et copier son 'id'")
        print()
        print("Etape 3: Remplacer EMAIL_ID dans ce script avec l'ID trouve")
        print()
        print("Etape 4: Relancer ce script")
        return

    print("=" * 70)
    print("TEST API /ANALYZE AVEC EMAIL 'CHIFFRAGE' REEL")
    print("=" * 70)
    print(f"Email ID: {EMAIL_ID}")
    print()

    # 1. Récupérer les détails de l'email d'abord
    print("--- Etape 1: Recuperer les details de l'email ---")
    try:
        r = requests.get(f"http://localhost:8001/api/graph/emails/{EMAIL_ID}")
        r.raise_for_status()
        email = r.json()

        print(f"Sujet: {email.get('subject', 'N/A')}")
        print(f"From: {email.get('from_address', 'N/A')}")
        print(f"Preview: {email.get('body_preview', 'N/A')[:100]}...")
        print()
    except Exception as e:
        print(f"ERREUR lors de la recuperation de l'email: {e}")
        print("Verifiez que:")
        print("  1. Le backend est lance (http://localhost:8001)")
        print("  2. L'EMAIL_ID est correct")
        return

    # 2. Analyser l'email avec force=true pour bypasser le cache
    print("--- Etape 2: Analyser l'email avec force=true ---")
    try:
        r = requests.post(
            f"http://localhost:8001/api/graph/emails/{EMAIL_ID}/analyze?force=true"
        )
        r.raise_for_status()
        analysis = r.json()

        print(f"Classification: {analysis.get('classification', 'N/A')}")
        print(f"Is quote request: {analysis.get('is_quote_request', 'N/A')}")
        print(f"Confidence: {analysis.get('confidence', 'N/A')}")
        print(f"Reasoning: {analysis.get('reasoning', 'N/A')}")
        print(f"Quick filter passed: {analysis.get('quick_filter_passed', 'N/A')}")
        print()

        # Vérifier le résultat
        is_detected = analysis.get('is_quote_request', False)
        classification = analysis.get('classification', '')

        print("=" * 70)
        if is_detected and classification == 'QUOTE_REQUEST':
            print("[OK] Email correctement detecte comme QUOTE_REQUEST")
            print("Le fix fonctionne! Le mot 'chiffrage' est maintenant reconnu.")
        else:
            print("[ERREUR] Email NON detecte comme QUOTE_REQUEST")
            print(f"Classification actuelle: {classification}")
            print(f"Is quote request: {is_detected}")
            print()
            print("DEBUG - Verifiez:")
            print("  1. Le backend a bien ete redémarre apres la modification")
            print("  2. Le fichier email_analyzer.py contient bien les nouveaux mots-cles")
            print("  3. L'email contient bien le mot 'chiffrage' dans le sujet ou le corps")
        print("=" * 70)

        # Afficher la réponse complète en JSON pour debug
        print()
        print("--- Reponse complete (JSON) ---")
        print(json.dumps(analysis, indent=2, ensure_ascii=False))

    except Exception as e:
        print(f"ERREUR lors de l'analyse: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_api_chiffrage()
