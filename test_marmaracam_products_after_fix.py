"""Test du nombre de produits extraits apres le fix de filtrage"""
import requests
import json

EMAIL_ID = "AAMkADI0Mjc0NDZmLTYyYmUtNGE0NC04YjEzLTM3NDk2NGYwNjFkNwBGAAAAAABJXEqH4KjITaiSBzfaWvvXBwAUuRiIdNuMSoMEzumJldkiAAAAAAEMAAAUuRiIdNuMSoMEzumJldkiAAAQdtcfAAA="

print("=" * 80)
print("TEST EXTRACTION PRODUITS APRES FIX FILTRAGE")
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
    print("RESULTAT CLIENT")
    print("=" * 80)

    # Verifier le client
    client_code = None
    client_name = None
    if analysis.get('extracted_data'):
        client_code = analysis['extracted_data'].get('client_card_code')
        client_name = analysis['extracted_data'].get('client_name')

    if client_code:
        is_marmara = 'marmara' in client_name.lower() if client_name else False
        if is_marmara:
            print(f"[OK] Client correct: {client_code} - {client_name}")
        else:
            print(f"[ERREUR] Client incorrect: {client_code} - {client_name}")
            print(f"         Attendu: C0249 - MARMARA CAM")
    else:
        print("[ERREUR] Aucun client trouve")

    print()
    print("=" * 80)
    print("RESULTAT PRODUITS")
    print("=" * 80)

    # Verifier les produits
    product_matches = analysis.get('product_matches', [])
    print(f"Nombre de produits extraits: {len(product_matches)}")
    print(f"Attendu: 28 produits")
    print()

    if len(product_matches) == 28:
        print("[OK] Nombre de produits CORRECT!")
    elif len(product_matches) < 28:
        print(f"[ATTENTION] Moins de produits ({len(product_matches)}) - peut-etre trop filtre?")
    else:
        print(f"[ATTENTION] Trop de produits ({len(product_matches)}) - des faux positifs restent")

    print()

    # Verifier les faux positifs connus
    false_positives_to_check = [
        "X-AXIS", "Y-AXIS", "Z-AXIS",
        "XAXIS", "YAXIS", "ZAXIS",
        "X-EKSENI", "Y-EKSENI",
        "ci-joint", "cijoint",
        "902826751020"
    ]

    print("Verification des faux positifs connus:")
    print("-" * 80)

    found_false_positives = []
    for fp in false_positives_to_check:
        # Chercher dans les item_code
        found = False
        for p in product_matches:
            item_code = p.get('item_code', '').upper().replace('-', '').replace('_', '')
            fp_normalized = fp.upper().replace('-', '').replace('_', '')

            if fp_normalized in item_code or item_code in fp_normalized:
                found = True
                found_false_positives.append((fp, p.get('item_code')))
                break

        if found:
            print(f"  [ERREUR] Faux positif presente: {fp} -> {p.get('item_code')}")
        else:
            print(f"  [OK] Faux positif filtre: {fp}")

    print()

    # Afficher tous les produits
    if len(product_matches) <= 50:
        print("Liste complete des produits extraits:")
        print("-" * 80)
        for i, p in enumerate(product_matches, 1):
            item_code = p.get('item_code', 'N/A')
            match_reason = p.get('match_reason', 'N/A')
            score = p.get('score', 0)
            print(f"  {i:2d}. {item_code:20s} (score: {score:3d}) - {match_reason[:50]}")

    print()
    print("=" * 80)
    print("RESUME")
    print("=" * 80)

    client_ok = client_code == "C0249" if client_code else False
    products_ok = len(product_matches) == 28
    no_false_positives = len(found_false_positives) == 0

    print(f"Client correct: {'OUI' if client_ok else 'NON'}")
    print(f"Nombre produits: {len(product_matches)}/28 {'OK' if products_ok else 'KO'}")
    print(f"Faux positifs: {len(found_false_positives)} trouvés {'KO' if found_false_positives else 'OK'}")

    print()

    if client_ok and (products_ok or abs(len(product_matches) - 28) <= 3) and no_false_positives:
        print("[SUCCES] Email MarmaraCam analyse correctement!")
    else:
        print("[ATTENTION] Il reste des problemes a corriger")

except Exception as e:
    print(f"[ERREUR] {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
