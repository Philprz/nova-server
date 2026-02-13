"""Test du filtrage des faux positifs dans l'extraction de produits"""
import asyncio
from services.email_analyzer import get_email_analyzer

async def test_product_filtering():
    """Test avec les vrais faux positifs de l'email MarmaraCam"""

    print("=" * 80)
    print("TEST FILTRAGE FAUX POSITIFS - EXTRACTION PRODUITS")
    print("=" * 80)
    print()

    analyzer = get_email_analyzer()

    # Texte simulé contenant les faux positifs réels
    body_with_false_positives = """
    Demande de chiffrage pour les produits suivants:

    Produits réels (à garder):
    - HST-117-03 SIZE 3 PUSHER BLADE
    - BT-119-05 SIZE 5 BEARING
    - AB123456 VALVE ASSY
    - REF: XY789012 GASKET SET

    Faux positifs (à filtrer):
    - X-AXIS calibration (terme machine)
    - Y-AXIS movement (terme machine)
    - Z-AXIS position (terme machine)
    - X-EKSENİ hareket (turc: axe X)
    - Y-EKSENİ konum (turc: axe Y)
    - ci-joint le fichier (français: attached)
    - Fax: 902826751020 (numéro fax turc)
    - Tel: 0033612345678 (numéro français)

    Merci de nous faire un devis.
    """

    print("Test 1: Vérification _is_phone_number")
    print("-" * 80)
    test_numbers = [
        ("902826751020", True, "Fax turc (12 chiffres)"),
        ("0033612345678", True, "Téléphone français international"),
        ("0612345678", True, "Téléphone français"),
        ("HST11703", False, "Code produit alphanumérique"),
        ("AB123456", False, "Code produit"),
    ]

    for code, should_be_phone, description in test_numbers:
        is_phone = analyzer._is_phone_number(code)
        status = "OK" if is_phone == should_be_phone else "ERREUR"
        print(f"  [{status}] {code:20s} -> {is_phone:5} (attendu: {should_be_phone:5}) - {description}")

    print()
    print("Test 2: Vérification _is_false_positive_product")
    print("-" * 80)

    test_false_positives = [
        ("X-AXIS", True, "Terme machine anglais"),
        ("Y-AXIS", True, "Terme machine anglais"),
        ("Z-AXIS", True, "Terme machine anglais"),
        ("X-EKSENİ", True, "Terme machine turc"),
        ("Y-EKSENİ", True, "Terme machine turc"),
        ("ci-joint", True, "Mot français courant"),
        ("HST-117-03", False, "Code produit valide"),
        ("AB123456", False, "Code produit valide"),
        ("BT-119-05", False, "Code produit valide"),
    ]

    for code, should_be_fp, description in test_false_positives:
        is_fp = analyzer._is_false_positive_product(code)
        status = "OK" if is_fp == should_be_fp else "ERREUR"
        print(f"  [{status}] {code:20s} -> {is_fp:5} (attendu: {should_be_fp:5}) - {description}")

    print()
    print("Test 3: Extraction complète avec filtrage")
    print("-" * 80)

    # Extraire les produits
    products = analyzer._extract_products_from_text(body_with_false_positives)

    print(f"Produits extraits: {len(products)}")
    print()

    # Vérifier que les bons produits sont là
    expected_products = ["HST-117-03", "BT-119-05", "AB123456", "XY789012"]
    found_refs = [p.reference for p in products]

    for expected in expected_products:
        if expected in found_refs:
            print(f"  [OK] Produit valide trouvé: {expected}")
        else:
            print(f"  [MANQUANT] Produit valide NON trouvé: {expected}")

    print()

    # Vérifier que les faux positifs sont absents
    unwanted_items = ["X-AXIS", "Y-AXIS", "Z-AXIS", "X-EKSENI", "Y-EKSENI", "ci-joint", "902826751020"]

    for unwanted in unwanted_items:
        # Normaliser pour comparaison
        unwanted_normalized = unwanted.upper().replace('-', '')
        found = any(unwanted_normalized in ref.replace('-', '') for ref in found_refs)

        if not found:
            print(f"  [OK] Faux positif filtré: {unwanted}")
        else:
            print(f"  [ERREUR] Faux positif présent: {unwanted}")

    print()
    print("=" * 80)
    print("RÉSUMÉ")
    print("=" * 80)

    # Compter les vrais produits vs faux positifs attendus
    expected_count = len(expected_products)
    actual_count = len(products)

    if actual_count == expected_count:
        print(f"[OK] Nombre de produits correct: {actual_count}/{expected_count}")
    else:
        print(f"[ATTENTION] Nombre de produits: {actual_count} (attendu: {expected_count})")
        print()
        print("Produits extraits:")
        for p in products:
            print(f"  - {p.reference}: {p.description}")

    print()

if __name__ == "__main__":
    asyncio.run(test_product_filtering())
