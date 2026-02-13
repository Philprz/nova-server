"""Test simple sans probleme Unicode"""
import requests
import json

EMAIL_ID = "AAMkADI0Mjc0NDZmLTYyYmUtNGE0NC04YjEzLTM3NDk2NGYwNjFkNwBGAAAAAABJXEqH4KjITaiSBzfaWvvXBwAUuRiIdNuMSoMEzumJldkiAAAAAAEMAAAUuRiIdNuMSoMEzumJldkiAAAQdtcfAAA="

print("Test simple - Comptage produits")
print("=" * 60)

try:
    r = requests.post(
        f"http://localhost:8001/api/graph/emails/{EMAIL_ID}/analyze?force=true",
        timeout=120
    )
    r.raise_for_status()
    analysis = r.json()

    products = analysis.get('product_matches', [])

    print(f"\nNombre total de produits: {len(products)}")
    print(f"Attendu: 28")
    print(f"Difference: {len(products) - 28:+d}")
    print()

    # Chercher specifiquement les termes turcs
    turkish_terms = []
    for p in products:
        item_code = p.get('item_code', '')
        # Remplacer les caracteres speciaux pour affichage
        safe_code = item_code.encode('ascii', 'ignore').decode('ascii')
        if 'EKSENI' in item_code.upper() or 'EKSEN' in item_code.upper():
            turkish_terms.append(item_code)
            print(f"[PROBLEME] Terme turc trouve: {safe_code} (caracteres speciaux supprimes)")

    if not turkish_terms:
        print("[OK] Aucun terme turc (X-EKSENI, Y-EKSENI) trouve")
    else:
        print(f"\n[ERREUR] {len(turkish_terms)} terme(s) turc(s) encore present(s)")

    print()
    print("Liste TOUS les codes produits (ASCII safe):")
    for i, p in enumerate(products, 1):
        item_code = p.get('item_code', '')
        # Convertir en ASCII safe
        safe_code = item_code.encode('ascii', 'replace').decode('ascii')
        print(f"  {i:2d}. {safe_code}")

except Exception as e:
    print(f"[ERREUR] {e}")
    import traceback
    traceback.print_exc()
