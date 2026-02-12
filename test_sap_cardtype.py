"""
Script de test pour déterminer les valeurs de CardType dans SAP B1
"""
import asyncio
from services.sap_business_service import get_sap_business_service

async def test_cardtypes():
    sap = get_sap_business_service()

    print("=== Test 1: Premiers BusinessPartners (sans filtre) ===")
    try:
        result = await sap._call_sap("/BusinessPartners", params={
            "$select": "CardCode,CardName,CardType",
            "$top": 10
        })

        print(f"Résultats: {len(result.get('value', []))} BusinessPartners")

        # Analyser les types
        types = {}
        for bp in result.get('value', []):
            card_type = bp.get('CardType', 'N/A')
            if card_type not in types:
                types[card_type] = []
            types[card_type].append(f"{bp['CardCode']} - {bp['CardName']}")

        print("\nTypes trouvés:")
        for type_name, bps in types.items():
            print(f"\n  {type_name}: {len(bps)} BP(s)")
            for bp in bps[:3]:
                print(f"    - {bp}")
    except Exception as e:
        print(f"Erreur: {e}")

    print("\n=== Test 2: Rechercher SAVERGLASS ===")
    try:
        result = await sap._call_sap("/BusinessPartners", params={
            "$select": "CardCode,CardName,CardType,EmailAddress",
            "$filter": "startswith(CardName, 'SAVERGLASS')",
            "$top": 10
        })

        print(f"Résultats SAVERGLASS: {len(result.get('value', []))}")
        for bp in result.get('value', []):
            print(f"  {bp['CardCode']} - {bp['CardName']} (Type: {bp.get('CardType')}, Email: {bp.get('EmailAddress')})")
    except Exception as e:
        print(f"Erreur: {e}")

if __name__ == "__main__":
    asyncio.run(test_cardtypes())
