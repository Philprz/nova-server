"""
Script pour analyser un email et calculer les prix automatiquement
"""

import httpx
import asyncio
import json

async def analyze_email():
    async with httpx.AsyncClient(timeout=60.0) as client:
        # 1. Récupérer la liste des emails
        print("[INFO] Recuperation des emails...")
        response = await client.get("http://localhost:8001/api/graph/emails?folder=inbox&limit=50")

        if response.status_code != 200:
            print(f"[ERREUR] Erreur recuperation emails: {response.status_code}")
            return

        emails = response.json()["emails"]

        # 2. Trouver l'email SAVERGLASS
        email_id = None
        for email in emails:
            if "2323060165" in email.get("body_preview", ""):
                email_id = email["id"]
                print(f"[OK] Email trouve: {email['subject'][:50]}")
                print(f"     ID: {email_id[:50]}...")
                break

        if not email_id:
            print("[ERREUR] Email SAVERGLASS non trouve")
            return

        # 3. Lancer l'analyse complète (avec Phase 5 - pricing automatique)
        print(f"\n[ANALYSE] Lancement analyse complete avec pricing (FORCE=TRUE)...")
        response = await client.post(
            f"http://localhost:8001/api/graph/emails/{email_id}/analyze?force=true"
        )

        print(f"[INFO] Statut: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print(f"[OK] Analyse terminee !")
            print(f"     Classification: {result.get('classification')}")
            print(f"     Devis: {result.get('is_quote_request')}")

            # Afficher les données extraites brutes
            if result.get('extracted_data'):
                extracted = result['extracted_data']
                print(f"\n[EXTRACTION] Donnees extraites:")
                print(f"     Client: {extracted.get('client_name')}")
                print(f"     Email client: {extracted.get('client_email')}")

                if extracted.get('products'):
                    print(f"     Produits extraits: {len(extracted['products'])}")
                    for prod in extracted['products']:
                        print(f"        - Ref: {prod.get('reference')} | Desc: {prod.get('description')[:40]} | Qte: {prod.get('quantity')}")
                else:
                    print(f"     Produits extraits: AUCUN")

            # Afficher les clients trouvés
            if result.get('client_matches'):
                print(f"\n[CLIENTS] {len(result['client_matches'])} client(s) trouve(s):")
                for client in result['client_matches'][:3]:
                    print(f"     - {client.get('card_code')}: {client.get('card_name')} (score: {client.get('score')}%)")

            # Afficher les produits avec prix
            if result.get('product_matches'):
                print(f"\n[PRODUITS] {len(result['product_matches'])} produit(s) trouve(s):")
                for product in result['product_matches']:
                    item_code = product.get('item_code', 'N/A')
                    item_name = product.get('item_name', 'N/A')[:40]
                    quantity = product.get('quantity', 0)
                    unit_price = product.get('unit_price')
                    pricing_case = product.get('pricing_case')

                    print(f"     - {item_code}: {item_name}")
                    print(f"       Quantite: {quantity}")

                    if unit_price is not None:
                        print(f"       Prix: {unit_price:.2f} EUR (CAS: {pricing_case})")
                        print(f"       Total: {(unit_price * quantity):.2f} EUR")
                    else:
                        print(f"       Prix: AUCUN PRIX CALCULE")

            else:
                print("[ATTENTION] Aucun produit trouve dans l'analyse")

        else:
            error = response.json()
            print(f"[ERREUR] {error.get('detail', 'Erreur inconnue')}")

if __name__ == "__main__":
    asyncio.run(analyze_email())
