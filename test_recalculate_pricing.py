"""
Script de test pour l'endpoint recalculate-pricing
"""

import httpx
import asyncio
import json

async def test_recalculate():
    # 1. Récupérer la liste des emails
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("[INFO] Recuperation des emails...")
        response = await client.get("http://localhost:8000/api/graph/emails?folder=inbox&limit=50")

        if response.status_code != 200:
            print(f"[ERREUR] Erreur récupération emails: {response.status_code}")
            return

        emails = response.json()["emails"]

        # 2. Trouver l'email SAVERGLASS
        email_id = None
        for email in emails:
            if "2323060165" in email.get("body_preview", ""):
                email_id = email["id"]
                print(f"[OK] Email trouvé: {email['subject'][:50]}")
                print(f"   ID: {email_id[:30]}...")
                break

        if not email_id:
            print("[ERREUR] Email SAVERGLASS non trouvé")
            print("   Emails disponibles:")
            for email in emails[:5]:
                print(f"   - {email['subject'][:60]}")
            return

        # 3. Tester le recalcul des prix
        print(f"\n[PRICING] Test recalcul pricing...")
        response = await client.post(
            f"http://localhost:8000/api/graph/emails/{email_id}/recalculate-pricing"
        )

        print(f"   Statut: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print(f"[OK] Succès !")
            print(f"   Prix calculés: {result['pricing_calculated']}/{result['total_products']}")
            print(f"   Durée: {result['duration_ms']:.0f}ms")

            if result.get('errors'):
                print(f"   Erreurs: {result['errors']}")

            # Afficher les prix calculés
            if result.get('analysis', {}).get('product_matches'):
                print(f"\n[PRODUITS] Produits avec prix:")
                for product in result['analysis']['product_matches']:
                    item_code = product.get('item_code', 'N/A')
                    unit_price = product.get('unit_price')
                    pricing_case = product.get('pricing_case', 'N/A')

                    if unit_price:
                        print(f"   - {item_code}: {unit_price:.2f} EUR ({pricing_case})")
                    else:
                        print(f"   - {item_code}: AUCUN PRIX")
        else:
            error = response.json()
            print(f"[ERREUR] Erreur: {error.get('detail', 'Erreur inconnue')}")

if __name__ == "__main__":
    asyncio.run(test_recalculate())
