"""Test de l'endpoint export v2 pre-sap-quote"""
import requests
import json

EMAIL_ID = "AAMkADI0Mjc0NDZmLTYyYmUtNGE0NC04YjEzLTM3NDk2NGYwNjFkNwBGAAAAAABJXEqH4KjITaiSBzfaWvvXBwAUuRiIdNuMSoMEzumJldkiAAAAAAEMAAAUuRiIdNuMSoMEzumJldkiAAAQdtcfAAA="

print("=" * 80)
print("TEST EXPORT V2 PRE-SAP-QUOTE")
print("=" * 80)

try:
    response = requests.get(
        f"http://localhost:8001/api/export-v2/pre-sap-quote/{EMAIL_ID}",
        timeout=120
    )

    print(f"\nStatus Code: {response.status_code}")

    if response.status_code == 200:
        data = response.json()

        print("\n✅ SUCCESS - Pre-SAP Quote JSON généré!")
        print("\n" + "=" * 80)
        print("BUSINESS PARTNER:")
        print("=" * 80)
        bp = data.get("business_partner", {})
        print(f"  CardCode: {bp.get('CardCode')}")
        print(f"  CardName: {bp.get('CardName')}")
        print(f"  ContactEmail: {bp.get('ContactEmail')}")
        print(f"  ToBeCreated: {bp.get('ToBeCreated')}")

        print("\n" + "=" * 80)
        print("DOCUMENT LINES:")
        print("=" * 80)
        lines = data.get("document_lines", [])
        print(f"  Nombre de produits: {len(lines)}")
        print("\n  Premiers produits:")
        for i, line in enumerate(lines[:10], 1):
            print(f"    {i:2d}. {line.get('ItemCode'):15s} - {line.get('ItemDescription', '')[:50]}")

        if len(lines) > 10:
            print(f"    ... ({len(lines) - 10} autres produits)")

        print("\n" + "=" * 80)
        print("META:")
        print("=" * 80)
        meta = data.get("meta", {})
        print(f"  Classification: {meta.get('classification')}")
        print(f"  Confidence: {meta.get('confidence_level')}")
        print(f"  Client Score: {meta.get('client_score')}/100")
        print(f"  Product Count: {meta.get('product_count')}")
        print(f"  Manual Validation Required: {meta.get('manual_validation_required')}")
        print(f"  False Positives Filtered: {meta.get('false_positives_filtered')}")

        # Vérifications
        print("\n" + "=" * 80)
        print("VÉRIFICATIONS:")
        print("=" * 80)

        checks = []

        # Vérifier CardCode
        if bp.get('CardCode') == 'C0249':
            checks.append("✅ CardCode correct: C0249 (MARMARA CAM)")
        else:
            checks.append(f"❌ CardCode incorrect: {bp.get('CardCode')} (attendu: C0249)")

        # Vérifier nombre de produits
        expected_count = 34  # Après filtrage
        actual_count = len(lines)
        if actual_count == expected_count:
            checks.append(f"✅ Nombre de produits correct: {actual_count}")
        else:
            checks.append(f"⚠️  Nombre de produits: {actual_count} (attendu: {expected_count})")

        # Vérifier classification
        if meta.get('classification') == 'QUOTE_REQUEST':
            checks.append("✅ Classification correcte: QUOTE_REQUEST")
        else:
            checks.append(f"❌ Classification incorrecte: {meta.get('classification')}")

        # Vérifier faux positifs filtrés
        if meta.get('false_positives_filtered'):
            checks.append("✅ Faux positifs filtrés")
        else:
            checks.append("❌ Faux positifs non filtrés")

        for check in checks:
            print(f"  {check}")

        print("\n" + "=" * 80)
        if all("✅" in check for check in checks):
            print("🎯 TOUS LES TESTS PASSENT - READY FOR DEMO!")
        else:
            print("⚠️  Quelques tests échouent - vérifier les détails ci-dessus")
        print("=" * 80)

        # Sauvegarder le JSON complet
        with open("pre-sap-quote-export.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print("\n✅ JSON complet sauvegardé dans: pre-sap-quote-export.json")

    else:
        print(f"\n❌ ERREUR: {response.status_code}")
        print(response.text)

except requests.exceptions.ConnectionError:
    print("\n❌ ERREUR: Impossible de se connecter au backend")
    print("   Vérifiez que le backend est démarré sur http://localhost:8001")
except Exception as e:
    print(f"\n❌ ERREUR: {e}")
    import traceback
    traceback.print_exc()
