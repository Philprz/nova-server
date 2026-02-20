"""
Test du traitement d'un email avec plusieurs produits
Vérifie que chaque produit est analysé, matché et pricé correctement
"""

import httpx
import asyncio
import json


async def test_multi_products():
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Récupérer les emails
        print("[INFO] Récupération des emails...")
        response = await client.get("http://localhost:8001/api/graph/emails?folder=inbox&limit=50")

        if response.status_code != 200:
            print(f"[ERREUR] Erreur récupération: {response.status_code}")
            return

        emails = response.json()["emails"]

        # Lister les emails avec pièces jointes
        print("\n[EMAILS] Emails avec pièces jointes:")
        for email in emails[:10]:
            has_pdf = "attachment" in email.get("body_preview", "").lower() or email.get("has_attachments", False)
            if has_pdf:
                print(f"  - {email['subject'][:60]}")
                print(f"    ID: {email['id'][:50]}...")
                print(f"    Pièces jointes: {email.get('has_attachments', 'N/A')}")

        # Demander à l'utilisateur quel email analyser
        print("\n[INFO] Entrez l'ID de l'email à analyser (ou 'saverglass' pour l'email test):")
        choice = input("> ").strip()

        email_id = None
        if choice.lower() == "saverglass":
            # Chercher l'email SAVERGLASS
            for email in emails:
                if "2323060165" in email.get("body_preview", ""):
                    email_id = email["id"]
                    print(f"[OK] Email SAVERGLASS trouvé: {email['subject']}")
                    break
        else:
            email_id = choice

        if not email_id:
            print("[ERREUR] Email non trouvé")
            return

        # Analyser l'email
        print(f"\n[ANALYSE] Lancement analyse complète avec pricing...")
        response = await client.post(
            f"http://localhost:8001/api/graph/emails/{email_id}/analyze?force=true"
        )

        if response.status_code != 200:
            error = response.json()
            print(f"[ERREUR] {error.get('detail', 'Erreur inconnue')}")
            return

        result = response.json()
        print(f"[OK] Analyse terminée!")
        print(f"  Classification: {result.get('classification')}")

        # Afficher les produits extraits
        if result.get("extracted_data", {}).get("products"):
            products = result["extracted_data"]["products"]
            print(f"\n[EXTRACTION] {len(products)} produit(s) extrait(s) du texte/PDF:")
            for i, prod in enumerate(products, 1):
                print(f"  {i}. Ref: {prod.get('reference', 'N/A')}")
                print(f"     Desc: {prod.get('description', 'N/A')[:60]}")
                print(f"     Qté: {prod.get('quantity', 'N/A')} {prod.get('unit', '')}")

        # Afficher les produits matchés SAP
        if result.get("product_matches"):
            matches = result["product_matches"]
            print(f"\n[SAP] {len(matches)} produit(s) matché(s) dans SAP:")

            total_with_price = 0
            total_ht = 0.0

            for i, match in enumerate(matches, 1):
                item_code = match.get("item_code", "N/A")
                item_name = match.get("item_name", "N/A")[:50]
                quantity = match.get("quantity", 1)
                unit_price = match.get("unit_price")
                supplier_price = match.get("supplier_price")
                pricing_case = match.get("pricing_case", "N/A")
                margin = match.get("margin_applied")

                print(f"\n  {i}. {item_code} - {item_name}")
                print(f"     Quantité: {quantity}")

                if unit_price:
                    total_with_price += 1
                    line_total = unit_price * quantity
                    total_ht += line_total

                    print(f"     [OK] Prix unitaire: {unit_price:.2f} EUR ({pricing_case})")
                    print(f"       Total ligne: {line_total:.2f} EUR")

                    if supplier_price:
                        print(f"       Prix fournisseur: {supplier_price:.2f} EUR")
                    if margin:
                        print(f"       Marge: {margin:.1f}%")

                    # Alertes
                    alerts = match.get("alerts", [])
                    if alerts:
                        for alert in alerts:
                            print(f"       [ALERTE] {alert}")
                else:
                    print(f"     [ERREUR] Aucun prix calcule")
                    if match.get("not_found_in_sap"):
                        print(f"       Raison: Article non trouvé dans SAP")

            # Resume
            print(f"\n[RESUME]")
            print(f"  Produits avec prix: {total_with_price}/{len(matches)}")
            print(f"  Total HT: {total_ht:.2f} EUR")
            print(f"  Taux pricing reussi: {(total_with_price/len(matches)*100):.0f}%")

        else:
            print("\n[ATTENTION] Aucun produit trouvé dans l'analyse")


if __name__ == "__main__":
    asyncio.run(test_multi_products())
