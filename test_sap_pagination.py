"""
Test de pagination SAP pour comprendre la limite réelle
"""
import asyncio
from services.sap_business_service import get_sap_business_service

async def test_pagination():
    sap = get_sap_business_service()

    print("=== Test avec différentes valeurs de $top ===\n")

    for top_value in [20, 50, 100, 200]:
        try:
            result = await sap._call_sap("/BusinessPartners", params={
                "$select": "CardCode,CardName",
                "$filter": "CardType eq 'cCustomer'",
                "$top": top_value,
                "$skip": 0
            })

            count = len(result.get('value', []))
            print(f"$top={top_value:3d} -> Résultats reçus: {count}")

        except Exception as e:
            print(f"$top={top_value:3d} -> Erreur: {e}")

    print("\n=== Test de pagination complète ===\n")

    all_clients = []
    skip = 0
    batch_size = 20  # Utiliser la vraie limite SAP

    while True:
        result = await sap._call_sap("/BusinessPartners", params={
            "$select": "CardCode,CardName",
            "$filter": "CardType eq 'cCustomer'",
            "$top": batch_size,
            "$skip": skip,
            "$orderby": "CardCode"
        })

        batch = result.get('value', [])
        if not batch:
            break

        all_clients.extend(batch)
        print(f"Skip={skip:4d}: Reçu {len(batch)} clients (Total: {len(all_clients)})")

        skip += batch_size

        if len(batch) < batch_size:
            print(f"\nDernière page atteinte (< {batch_size} résultats)")
            break

        if len(all_clients) >= 100:  # Limite pour le test
            print(f"\nTest limité à 100 clients")
            break

    print(f"\n✅ Total clients synchronisables: {len(all_clients)}")

    # Vérifier si SAVERGLASS C0023 est dans les résultats
    saverglass = [c for c in all_clients if 'SAVERGLASS' in c.get('CardName', '') and c.get('CardCode') == 'C0023']
    if saverglass:
        print(f"✅ SAVERGLASS C0023 trouvé à la position {all_clients.index(saverglass[0]) + 1}")
    else:
        print(f"❌ SAVERGLASS C0023 NON trouvé dans les {len(all_clients)} premiers clients")

if __name__ == "__main__":
    asyncio.run(test_pagination())
