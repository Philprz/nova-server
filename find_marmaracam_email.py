"""Script pour trouver l'email MarmaraCam et l'analyser directement"""
import requests
import json

def find_and_analyze():
    """Trouve l'email MarmaraCam et l'analyse avec force=true"""

    print("=" * 80)
    print("RECHERCHE EMAIL MARMARACAM")
    print("=" * 80)

    # 1. Récupérer tous les emails
    print("\n1. Recuperation de la liste des emails...")
    try:
        r = requests.get("http://localhost:8001/api/graph/emails?top=50")
        r.raise_for_status()
        emails = r.json()
        print(f"   [OK] {len(emails)} emails recuperes")
    except Exception as e:
        print(f"   [ERREUR] Impossible de recuperer les emails: {e}")
        print("   Verifiez que le backend est lance sur le port 8001")
        return

    # 2. Chercher l'email MarmaraCam
    print("\n2. Recherche de l'email MarmaraCam...")
    marmaracam_emails = []

    for email in emails:
        subject = email.get('subject', '').lower()
        if 'marmaracam' in subject or 'chiffrage' in subject:
            marmaracam_emails.append(email)
            print(f"   [TROUVE] {email.get('subject', 'N/A')}")
            print(f"            ID: {email.get('id', 'N/A')[:50]}...")
            print(f"            De: {email.get('from_name', 'N/A')}")
            print(f"            Preview: {email.get('body_preview', 'N/A')[:100]}...")
            print()

    if not marmaracam_emails:
        print("   [ERREUR] Aucun email contenant 'marmaracam' ou 'chiffrage' trouve!")
        print()
        print("   Emails disponibles:")
        for email in emails[:10]:
            print(f"     - {email.get('subject', 'N/A')}")
        return

    # 3. Si plusieurs emails trouvés, demander lequel analyser
    if len(marmaracam_emails) > 1:
        print(f"   {len(marmaracam_emails)} emails trouves contenant 'marmaracam' ou 'chiffrage'")
        print("   Le script analysera le premier de la liste.")
        print()

    target_email = marmaracam_emails[0]
    email_id = target_email['id']

    print("=" * 80)
    print("ANALYSE DE L'EMAIL")
    print("=" * 80)
    print(f"Sujet: {target_email.get('subject', 'N/A')}")
    print(f"De: {target_email.get('from_name', 'N/A')} <{target_email.get('from_address', 'N/A')}>")
    print(f"ID: {email_id}")
    print()

    # 4. Analyser avec force=true
    print("3. Analyse avec force=true (bypass cache)...")
    try:
        r = requests.post(
            f"http://localhost:8001/api/graph/emails/{email_id}/analyze?force=true"
        )
        r.raise_for_status()
        analysis = r.json()

        print()
        print("=" * 80)
        print("RESULTAT DE L'ANALYSE")
        print("=" * 80)
        print(f"Classification: {analysis.get('classification', 'N/A')}")
        print(f"Is quote request: {analysis.get('is_quote_request', 'N/A')}")
        print(f"Confidence: {analysis.get('confidence', 'N/A')}")
        print(f"Quick filter passed: {analysis.get('quick_filter_passed', 'N/A')}")
        print()
        print(f"Reasoning:")
        print(f"  {analysis.get('reasoning', 'N/A')}")
        print()

        # Vérifier le résultat
        is_quote = analysis.get('is_quote_request', False)
        classification = analysis.get('classification', '')

        print("=" * 80)
        if is_quote and classification == 'QUOTE_REQUEST':
            print("[OK] EMAIL CORRECTEMENT DETECTE COMME DEVIS!")
            print("Le probleme etait probablement le cache.")
            print()
            print("PROCHAINE ETAPE:")
            print("  - Rafraichir la page dans le navigateur (F5)")
            print("  - L'email devrait maintenant apparaitre comme 'Devis detecte'")
        else:
            print("[PROBLEME] EMAIL TOUJOURS CLASSE COMME NON PERTINENT")
            print()
            print(f"Classification: {classification}")
            print(f"Is quote request: {is_quote}")
            print()
            print("DIAGNOSTIC:")
            print("  Le code de detection ne reconnait pas cet email comme un devis.")
            print("  Verifiez:")
            print(f"    - Sujet contient 'chiffrage'? {('chiffrage' in target_email.get('subject', '').lower())}")
            print(f"    - Body preview: {target_email.get('body_preview', 'N/A')[:200]}")
            print()
            print("REPONSE COMPLETE:")
            print(json.dumps(analysis, indent=2, ensure_ascii=False))
        print("=" * 80)

    except Exception as e:
        print(f"[ERREUR] Analyse echouee: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    find_and_analyze()
