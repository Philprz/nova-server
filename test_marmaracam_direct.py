"""Test direct de l'email MarmaraCam via API"""
import requests
import json

EMAIL_ID = "AAMkADI0Mjc0NDZmLTYyYmUtNGE0NC04YjEzLTM3NDk2NGYwNjFkNwBGAAAAAABJXEqH4KjITaiSBzfaWvvXBwAUuRiIdNuMSoMEzumJldkiAAAAAAEMAAAUuRiIdNuMSoMEzumJldkiAAAQdtcfAAA="

print("=" * 80)
print("TEST DIRECT EMAIL MARMARACAM")
print("=" * 80)
print(f"Email ID: {EMAIL_ID[:50]}...")
print()

print("Analyse en cours (avec force=true pour bypass cache)...")
try:
    r = requests.post(
        f"http://localhost:8001/api/graph/emails/{EMAIL_ID}/analyze?force=true",
        timeout=180  # 3 minutes pour laisser le temps aux pièces jointes
    )
    r.raise_for_status()
    analysis = r.json()

    print()
    print("=" * 80)
    print("RESULTAT")
    print("=" * 80)
    print(f"Classification: {analysis.get('classification', 'N/A')}")
    print(f"Is quote request: {analysis.get('is_quote_request', 'N/A')}")
    print(f"Confidence: {analysis.get('confidence', 'N/A')}")
    print(f"Quick filter passed: {analysis.get('quick_filter_passed', 'N/A')}")
    print()
    print("Reasoning:")
    print(f"  {analysis.get('reasoning', 'N/A')}")
    print()

    is_quote = analysis.get('is_quote_request', False)
    classification = analysis.get('classification', '')

    print("=" * 80)
    if is_quote and classification == 'QUOTE_REQUEST':
        print("[OK] EMAIL DETECTE COMME DEVIS!")
        print()
        print("Le probleme etait le cache. Rafraichissez la page (F5).")
    else:
        print("[PROBLEME] EMAIL CLASSE COMME NON PERTINENT")
        print()
        print("Reponse complete:")
        print(json.dumps(analysis, indent=2, ensure_ascii=False))
    print("=" * 80)

except requests.exceptions.Timeout:
    print("[ERREUR] Timeout - l'analyse prend plus de 180 secondes")
    print("Cela peut arriver si:")
    print("  - L'email a une grosse piece jointe PDF")
    print("  - L'API LLM (Claude/OpenAI) est lente")
    print()
    print("Verifiez les logs backend pour plus de details.")
except Exception as e:
    print(f"[ERREUR] {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
