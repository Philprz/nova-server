"""
Vérification spécifique du fix Marmara après redémarrage serveur.
Re-analyse l'email Marmara pour vérifier que les 34 produits sont matchés et pricés.
"""

import asyncio
import httpx


async def verify_marmara_fix():
    print("=" * 70)
    print("VERIFICATION FIX MARMARA - APRÈS REDÉMARRAGE SERVEUR")
    print("=" * 70)

    async with httpx.AsyncClient(timeout=120.0) as client:
        # 1. Récupérer emails
        print("\n[1/3] Recherche email Marmara...")
        response = await client.get("http://localhost:8001/api/graph/emails?folder=inbox&limit=10")

        if response.status_code != 200:
            print(f"  [ERREUR] Impossible de récupérer les emails: {response.status_code}")
            return False

        emails = response.json()["emails"]
        marmara_id = None

        for email in emails:
            if "Marmara" in email.get("subject", ""):
                marmara_id = email["id"]
                print(f"  [OK] Email trouvé: {email['subject']}")
                break

        if not marmara_id:
            print("  [ERREUR] Email Marmara non trouvé dans inbox")
            return False

        # 2. Supprimer cache ancien
        print("\n[2/3] Suppression cache ancien...")
        try:
            delete_response = await client.delete(
                f"http://localhost:8001/api/graph/emails/{marmara_id}/cache"
            )
            if delete_response.status_code == 200:
                print("  [OK] Cache supprimé")
            else:
                print("  [INFO] Pas de cache à supprimer")
        except Exception as e:
            print(f"  [INFO] Pas de cache à supprimer ({e})")

        # 3. Re-analyser avec force=true
        print("\n[3/3] Re-analyse complète avec force=true...")
        print("  (Peut prendre 30-60 secondes pour 34 produits)")

        analysis_response = await client.post(
            f"http://localhost:8001/api/graph/emails/{marmara_id}/analyze?force=true"
        )

        if analysis_response.status_code != 200:
            error = analysis_response.json()
            print(f"  [ERREUR] Analyse échouée: {error.get('detail', 'Erreur inconnue')}")
            return False

        result = analysis_response.json()

        # 4. Vérifier résultats
        print("\n" + "=" * 70)
        print("RESULTATS")
        print("=" * 70)

        products = result.get("product_matches", [])
        print(f"\nTotal produits: {len(products)}")

        found_in_sap = [p for p in products if not p.get("not_found_in_sap", True)]
        not_found = [p for p in products if p.get("not_found_in_sap", True)]

        print(f"  Trouvés dans SAP: {len(found_in_sap)}/{len(products)}")
        print(f"  Non trouvés: {len(not_found)}/{len(products)}")

        if len(found_in_sap) > 0:
            print(f"\n[OK] FIX FONCTIONNE - {len(found_in_sap)} produits matchés !")

            # Afficher exemples
            print("\nExemples produits matchés:")
            for p in found_in_sap[:5]:
                price_info = f"{p.get('unit_price', 0):.2f} EUR" if p.get('unit_price') else "Prix à calculer"
                print(f"  - {p.get('item_code')}: {p.get('item_name', '')[:40]}... ({price_info})")

            # Vérifier pricing
            with_price = [p for p in found_in_sap if p.get('unit_price')]
            print(f"\nProduits avec prix: {len(with_price)}/{len(found_in_sap)}")

            if len(with_price) > 0:
                total_ht = sum(p.get('line_total', 0) for p in with_price)
                print(f"Total HT: {total_ht:.2f} EUR")

            if len(not_found) > 0:
                print(f"\n[ATTENTION] {len(not_found)} produits toujours non trouvés:")
                for p in not_found[:3]:
                    print(f"  - {p.get('item_code')}: {p.get('item_name', '')[:40]}...")

            return True

        else:
            print("\n[ERREUR] FIX NON APPLIQUÉ - Aucun produit matché")
            print("Vérifiez que le serveur a bien été redémarré !")
            return False


if __name__ == "__main__":
    success = asyncio.run(verify_marmara_fix())
    exit(0 if success else 1)
