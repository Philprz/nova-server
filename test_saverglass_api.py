"""Test API pour SAVERGLASS - debug complet"""
import requests
import json

email_id = "AAMkADI0Mjc0NDZmLTYyYmUtNGE0NC04YjEzLTM3NDk2NGYwNjFkNwBGAAAAAABJXEqH4KjITaiSBzfaWvvXBwAUuRiIdNuMSoMEzumJldkiAAAAAAEMAAAUuRiIdNuMSoMEzumJldkiAAANeDEFAAA="

print("="*60)
print("TEST ANALYSE EMAIL SAVERGLASS")
print("="*60)
print(f"Email ID: {email_id[:50]}...")

# 1. Récupérer les détails de l'email
print("\n1. Récupération email...")
r = requests.get(f"http://localhost:8001/api/graph/emails/{email_id}")
if r.status_code == 200:
    email = r.json()
    print(f"  Subject: {email['subject']}")
    print(f"  From: {email['from_address']}")
    print(f"  Body preview: {email['body_preview'][:100]}...")
else:
    print(f"  ERREUR: {r.status_code}")
    exit(1)

# 2. Analyser l'email
print("\n2. Analyse de l'email (force=true)...")
r = requests.post(f"http://localhost:8001/api/graph/emails/{email_id}/analyze?force=true")

if r.status_code != 200:
    print(f"  ERREUR HTTP {r.status_code}: {r.text}")
    exit(1)

result = r.json()

print("\nRésultat d'analyse:")
print("-"*60)
print(f"Classification: {result['classification']}")
print(f"Is quote request: {result['is_quote_request']}")
print(f"Confidence: {result['confidence']}")

if result.get('extracted_data'):
    ed = result['extracted_data']
    print(f"\nClient name: {ed.get('client_name')}")
    print(f"Client email: {ed.get('client_email')}")
    print(f"Client card code: {ed.get('client_card_code')}")  # ← CLEF !

    print(f"\nProducts: {len(ed.get('products', []))} trouvé(s)")
    for p in ed.get('products', []):
        print(f"  - {p['reference']}: {p['description']} (qty={p['quantity']})")

# 3. Vérifier les matches multiples
print("\nMatches multiples:")
print("-"*60)
client_matches = result.get('client_matches', [])
product_matches = result.get('product_matches', [])

print(f"Client matches: {len(client_matches)}")
for c in client_matches[:5]:
    print(f"  - {c['card_code']}: {c['card_name']} (score={c['score']}, raison={c['match_reason']})")

print(f"\nProduct matches: {len(product_matches)}")
for p in product_matches[:5]:
    print(f"  - {p['item_code']}: {p.get('item_name', 'N/A')} (score={p['score']})")

# 4. Validation auto
print("\nAuto-validation:")
print("-"*60)
print(f"Client auto-validated: {result.get('client_auto_validated', False)}")
print(f"Products auto-validated: {result.get('products_auto_validated', False)}")
print(f"Requires user choice: {result.get('requires_user_choice', False)}")
if result.get('user_choice_reason'):
    print(f"Reason: {result['user_choice_reason']}")

# 5. Diagnostic final
print("\n" + "="*60)
if ed.get('client_card_code'):
    print("✓ SUCCÈS - Client SAVERGLASS reconnu avec CardCode !")
else:
    print("✗ ÉCHEC - client_card_code est NULL")
    print("\nDébug:")
    print(f"  - Client matches trouvés: {len(client_matches)}")
    if client_matches:
        print(f"  - Meilleur match: {client_matches[0]['card_name']} (score={client_matches[0]['score']})")
    else:
        print("  - AUCUN client matché !")
print("="*60)
