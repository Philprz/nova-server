"""
Vérification complète du système Mail-to-Biz + Pricing
"""

import asyncio
import httpx
from pathlib import Path


async def check_system():
    print("=" * 70)
    print("VERIFICATION COMPLETE DU SYSTEME MAIL-TO-BIZ")
    print("=" * 70)

    results = {
        "backend_fixes": False,
        "frontend_build": False,
        "cache_sqlite": False,
        "pricing_saverglass": False,
        "matching_marmara": False
    }

    # 1. Vérifier les fichiers backend modifiés
    print("\n[1/5] VERIFICATION BACKEND")
    print("-" * 70)

    # email_matcher.py - SQLite fallback
    email_matcher_path = Path("services/email_matcher.py")
    if email_matcher_path.exists():
        content = email_matcher_path.read_text(encoding='utf-8')
        if "Fallback: Chercher dans le cache SQLite" in content:
            print("  [OK] email_matcher.py: SQLite fallback present")
            results["backend_fixes"] = True
        else:
            print("  [ERREUR] email_matcher.py: SQLite fallback MANQUANT")
    else:
        print("  [ERREUR] email_matcher.py: FICHIER INTROUVABLE")

    # MatchedProduct model
    if "decision_id: Optional[str]" in content and "sap_avg_price: Optional[float]" in content:
        print("  [OK] MatchedProduct: Champs pricing presents")
    else:
        print("  [ERREUR] MatchedProduct: Champs pricing MANQUANTS")
        results["backend_fixes"] = False

    # 2. Vérifier le build frontend
    print("\n[2/5] VERIFICATION FRONTEND BUILD")
    print("-" * 70)

    frontend_index = Path("frontend/index.html")
    if frontend_index.exists():
        html = frontend_index.read_text(encoding='utf-8')
        if "index-CvRMFbuM.js" in html:
            print("  [OK] Frontend build present (index-CvRMFbuM.js)")
            results["frontend_build"] = True
        else:
            print("  [ATTENTION] Frontend build different ou ancien")

    quotesummary_path = Path("mail-to-biz/src/components/QuoteSummary.tsx")
    if quotesummary_path.exists():
        tsx = quotesummary_path.read_text(encoding='utf-8')
        if "...pricing" in tsx:
            print("  [OK] QuoteSummary.tsx: Spread pricing present")
        else:
            print("  [ERREUR] QuoteSummary.tsx: Spread pricing MANQUANT")
            results["frontend_build"] = False

    # 3. Vérifier le cache SQLite
    print("\n[3/5] VERIFICATION CACHE SQLITE")
    print("-" * 70)

    try:
        from services.sap_cache_db import get_sap_cache_db
        cache = get_sap_cache_db()

        # Test produits Marmara
        test_codes = ['HST-117-03', 'TRI-038', 'C233-50AT10-1940G3']
        found = 0
        for code in test_codes:
            items = cache.search_items(code, limit=1)
            if items:
                found += 1

        if found == len(test_codes):
            print(f"  [OK] Cache SQLite: {found}/{len(test_codes)} produits Marmara trouves")
            results["cache_sqlite"] = True
        else:
            print(f"  [ATTENTION] Cache SQLite: {found}/{len(test_codes)} produits trouves")

    except Exception as e:
        print(f"  [ERREUR] Cache SQLite: {e}")

    # 4. Test pricing SAVERGLASS
    print("\n[4/5] TEST PRICING SAVERGLASS")
    print("-" * 70)

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Trouver email SAVERGLASS
            response = await client.get("http://localhost:8001/api/graph/emails?folder=inbox&limit=50")
            if response.status_code != 200:
                print("  [ERREUR] Impossible de recuperer les emails")
            else:
                emails = response.json()["emails"]
                saverglass_id = None

                for email in emails:
                    if "2323060165" in email.get("body_preview", ""):
                        saverglass_id = email["id"]
                        break

                if not saverglass_id:
                    print("  [ATTENTION] Email SAVERGLASS non trouve")
                else:
                    # Vérifier analyse
                    analysis_response = await client.get(
                        f"http://localhost:8001/api/graph/emails/{saverglass_id}/analysis"
                    )

                    if analysis_response.status_code == 200:
                        analysis = analysis_response.json()
                        products = analysis.get("product_matches", [])
                        with_price = sum(1 for p in products if p.get("unit_price"))

                        if products and with_price > 0:
                            product = products[0]
                            print(f"  [OK] Pricing SAVERGLASS: {with_price}/{len(products)} produits avec prix")
                            print(f"    Exemple: {product.get('item_code')} = {product.get('unit_price'):.2f} EUR")
                            print(f"    Prix fournisseur: {product.get('supplier_price', 'N/A')}")
                            print(f"    CAS: {product.get('pricing_case', 'N/A')}")
                            results["pricing_saverglass"] = True
                        else:
                            print(f"  [ERREUR] Pricing SAVERGLASS: 0 produits avec prix")
                    else:
                        print("  [ATTENTION] Email SAVERGLASS non analyse")

    except Exception as e:
        print(f"  [ERREUR] Test pricing SAVERGLASS: {e}")

    # 5. Test matching Marmara (après fix)
    print("\n[5/5] TEST MATCHING MARMARA")
    print("-" * 70)

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get("http://localhost:8001/api/graph/emails?folder=inbox&limit=5")
            emails = response.json()["emails"]

            marmara_id = None
            for email in emails:
                if "Marmara" in email.get("subject", ""):
                    marmara_id = email["id"]
                    break

            if not marmara_id:
                print("  [ATTENTION] Email Marmara non trouve")
            else:
                analysis_response = await client.get(
                    f"http://localhost:8001/api/graph/emails/{marmara_id}/analysis"
                )

                if analysis_response.status_code == 200:
                    analysis = analysis_response.json()
                    products = analysis.get("product_matches", [])
                    found_in_sap = sum(1 for p in products if not p.get("not_found_in_sap", True))
                    with_price = sum(1 for p in products if p.get("unit_price"))

                    print(f"  [INFO] Email Marmara: {len(products)} produits extraits")
                    print(f"    Trouves dans SAP: {found_in_sap}/{len(products)}")
                    print(f"    Avec prix: {with_price}/{len(products)}")

                    if found_in_sap > 0:
                        results["matching_marmara"] = True
                        print(f"  [OK] Matching Marmara: {found_in_sap} produits trouves")

                        # Afficher exemples
                        found_products = [p for p in products if not p.get("not_found_in_sap", True)][:3]
                        for p in found_products:
                            print(f"    - {p.get('item_code')}: {p.get('item_name', '')[:40]}")
                    else:
                        print("  [ERREUR] Matching Marmara: AUCUN produit trouve (fix non applique?)")
                else:
                    print("  [ATTENTION] Email Marmara non analyse")

    except Exception as e:
        print(f"  [ERREUR] Test matching Marmara: {e}")

    # RESUME
    print("\n" + "=" * 70)
    print("RESUME")
    print("=" * 70)

    total = len(results)
    passed = sum(1 for v in results.values() if v)

    for check, status in results.items():
        symbol = "[OK]" if status else "[ERREUR]"
        print(f"  {symbol} {check}")

    print(f"\nScore: {passed}/{total} ({passed/total*100:.0f}%)")

    if passed == total:
        print("\n[SUCCES] Tous les checks sont passes ! Le systeme est operationnel.")
        return True
    else:
        print(f"\n[ATTENTION] {total-passed} check(s) en echec. Verifiez les erreurs ci-dessus.")
        return False


if __name__ == "__main__":
    success = asyncio.run(check_system())
    exit(0 if success else 1)
