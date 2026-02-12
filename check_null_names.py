"""
Verifie les clients avec CardName NULL dans SAP
"""
import asyncio
from services.sap_business_service import get_sap_business_service

async def check_null_names():
    sap = get_sap_business_service()

    print("=== Verification CardName NULL ===\n")

    # Recuperer tous les clients
    all_clients = []
    skip = 0
    batch_size = 20

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
        skip += batch_size

        if len(batch) < batch_size:
            break

    # Analyser les CardName NULL
    null_names = [c for c in all_clients if not c.get("CardName")]
    empty_names = [c for c in all_clients if c.get("CardName") == ""]

    print(f"Total clients: {len(all_clients)}")
    print(f"CardName NULL: {len(null_names)}")
    print(f"CardName vide: {len(empty_names)}")

    if null_names:
        print(f"\nClients avec CardName NULL:")
        for c in null_names[:10]:  # Montrer les 10 premiers
            print(f"  - {c.get('CardCode')}: CardName = {c.get('CardName')}")

    if empty_names:
        print(f"\nClients avec CardName vide:")
        for c in empty_names[:10]:
            print(f"  - {c.get('CardCode')}: CardName = '{c.get('CardName')}'")

if __name__ == "__main__":
    asyncio.run(check_null_names())
