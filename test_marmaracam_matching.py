"""Test du matching client MarmaraCam après le fix"""
import requests
import json

EMAIL_ID = "AAMkADI0Mjc0NDZmLTYyYmUtNGE0NC04YjEzLTM3NDk2NGYwNjFkNwBGAAAAAABJXEqH4KjITaiSBzfaWvvXBwAUuRiIdNuMSoMEzumJldkiAAAAAAEMAAAUuRiIdNuMSoMEzumJldkiAAAQdtcfAAA="

print("=" * 80)
print("TEST MATCHING CLIENT MARMARACAM (APRÈS FIX)")
print("=" * 80)
print()

print("Analyse avec force=true...")
try:
    r = requests.post(
        f"http://localhost:8001/api/graph/emails/{EMAIL_ID}/analyze?force=true",
        timeout=120
    )
    r.raise_for_status()
    analysis = r.json()

    print()
    print("=" * 80)
    print("RÉSULTAT")
    print("=" * 80)

    # Vérifier les matches clients
    client_matches = analysis.get('client_matches', [])
    best_client_name = None
    best_client_code = None

    if analysis.get('extracted_data') and analysis['extracted_data'].get('client_card_code'):
        best_client_code = analysis['extracted_data']['client_card_code']
        best_client_name = analysis['extracted_data']['client_name']

    print(f"Nombre de clients matchés: {len(client_matches)}")
    print()

    if client_matches:
        print("Top 5 clients matchés (par score):")
        for i, client in enumerate(client_matches[:5], 1):
            marker = " ← SÉLECTIONNÉ" if client.get('card_code') == best_client_code else ""
            print(f"  {i}. {client.get('card_code')}: {client.get('card_name')}")
            print(f"     Score: {client.get('score')}")
            print(f"     Raison: {client.get('match_reason')}{marker}")
            print()

    print("=" * 80)

    # Vérifier si MarmaraCam est dans le top 3
    marmaracam_found = False
    marmaracam_position = None

    for i, client in enumerate(client_matches, 1):
        if 'marmara' in client.get('card_name', '').lower():
            marmaracam_found = True
            marmaracam_position = i
            break

    if marmaracam_found:
        if marmaracam_position == 1:
            print(f"✅ [OK] MarmaraCam est le client #1 (meilleur match)")
        else:
            print(f"⚠️  [WARNING] MarmaraCam est client #{marmaracam_position} (pas le meilleur)")
            print(f"    Le client #{1} est: {client_matches[0].get('card_name')}")
    else:
        print("❌ [ERREUR] MarmaraCam n'est PAS dans les matches!")
        print(f"   Le meilleur match est: {client_matches[0].get('card_name') if client_matches else 'Aucun'}")

    print("=" * 80)

    # Vérifier le nombre de produits
    product_matches = analysis.get('product_matches', [])
    print(f"\nProduits extraits: {len(product_matches)}")
    print(f"Attendu: 28 produits")

    if len(product_matches) == 28:
        print("✅ [OK] Nombre de produits correct!")
    else:
        print(f"❌ [ERREUR] {len(product_matches)} produits au lieu de 28")
        print("\nPremiers 10 produits:")
        for p in product_matches[:10]:
            print(f"  - {p.get('item_code')}: {p.get('match_reason', 'N/A')[:50]}")

except Exception as e:
    print(f"[ERREUR] {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
