"""
Test pour compter le nombre total de clients dans SAP B1
"""
import asyncio
from services.sap_business_service import get_sap_business_service

async def count_sap_clients():
    sap = get_sap_business_service()

    print("=== Comptage des clients SAP B1 ===\n")

    # Méthode 1: Utiliser $count pour obtenir le nombre total
    try:
        # SAP B1 supporte $count dans l'URL
        result = await sap._call_sap("/BusinessPartners/$count", params={
            "$filter": "CardType eq 'cCustomer'"
        })

        print(f"[OK] Methode 1 ($count): {result} clients")
    except Exception as e:
        print(f"[ERREUR] Methode 1 echouee: {e}")

    # Méthode 2: Utiliser $inlinecount=allpages
    try:
        result = await sap._call_sap("/BusinessPartners", params={
            "$select": "CardCode",
            "$filter": "CardType eq 'cCustomer'",
            "$top": 1,
            "$inlinecount": "allpages"
        })

        total = result.get("odata.count") or result.get("@odata.count")
        if total:
            print(f"[OK] Methode 2 (inlinecount): {total} clients")
        else:
            print(f"[WARN] Methode 2: Pas de compteur trouve dans la reponse")
            print(f"   Cles disponibles: {list(result.keys())}")
    except Exception as e:
        print(f"[ERREUR] Methode 2 echouee: {e}")

    # Méthode 3: Pagination complète pour compter manuellement
    print("\n=== Methode 3: Pagination complete ===")
    all_clients = []
    skip = 0
    batch_size = 20

    while True:
        result = await sap._call_sap("/BusinessPartners", params={
            "$select": "CardCode",
            "$filter": "CardType eq 'cCustomer'",
            "$top": batch_size,
            "$skip": skip,
            "$orderby": "CardCode"
        })

        batch = result.get('value', [])
        if not batch:
            break

        all_clients.extend(batch)
        print(f"  Skip {skip:4d}: {len(batch)} clients recuperes (Total: {len(all_clients)})")

        skip += batch_size

        if len(batch) < batch_size:
            break

    print(f"\n[OK] Total compte manuellement: {len(all_clients)} clients")

    # Vérifier la base SQLite
    from services.sap_cache_db import get_sap_cache_db
    cache_db = get_sap_cache_db()
    stats = cache_db.get_cache_stats()

    print(f"\n=== Comparaison ===")
    print(f"SAP B1:      {len(all_clients)} clients")
    print(f"Cache local: {stats['total_clients']} clients")

    if len(all_clients) > stats['total_clients']:
        print(f"[WARN] DIFFERENCE: {len(all_clients) - stats['total_clients']} clients manquants dans le cache!")
    elif len(all_clients) == stats['total_clients']:
        print(f"[OK] Cache synchronise correctement")
    else:
        print(f"[WARN] Cache contient PLUS de clients que SAP?!")

if __name__ == "__main__":
    asyncio.run(count_sap_clients())
