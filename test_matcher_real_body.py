"""Test du matcher avec le body HTML réel de SAVERGLASS"""
import asyncio
import requests
from services.email_matcher import get_email_matcher
from services.email_analyzer import get_email_analyzer

async def test():
    # 1. Récupérer l'email via API
    email_id = "AAMkADI0Mjc0NDZmLTYyYmUtNGE0NC04YjEzLTM3NDk2NGYwNjFkNwBGAAAAAABJXEqH4KjITaiSBzfaWvvXBwAUuRiIdNuMSoMEzumJldkiAAAAAAEMAAAUuRiIdNuMSoMEzumJldkiAAANeDEFAAA="

    print("="*60)
    print("TEST MATCHER AVEC BODY RÉEL")
    print("="*60)

    r = requests.get(f"http://localhost:8000/api/graph/emails/{email_id}")
    email = r.json()

    print(f"Subject: {email['subject']}")
    print(f"From: {email['from_address']}")
    print(f"Has body_content: {email['body_content'] is not None}")

    # 2. Si pas de body_content, récupérer le body complet
    if not email['body_content']:
        print("\nRécupération du body complet...")
        r2 = requests.get(f"http://localhost:8000/api/graph/emails/{email_id}/body")
        body_data = r2.json()
        body_text = body_data['body']
        body_type = body_data['type']
        print(f"Body type: {body_type}")
        print(f"Body length: {len(body_text)} caractères")
        print(f"Body preview: {body_text[:200]}...")
    else:
        body_text = email['body_content']
        body_type = email['body_content_type']

    # 3. Nettoyer le HTML avec _clean_html
    print("\n" + "="*60)
    print("NETTOYAGE HTML")
    print("="*60)
    analyzer = get_email_analyzer()
    clean_text = analyzer._clean_html(body_text)

    print(f"Clean text length: {len(clean_text)} caractères")
    print(f"Clean text preview:")
    print("-"*60)
    print(clean_text[:500])
    print("-"*60)

    # Vérifier que l'email est préservé
    if "chq@saverglass.com" in clean_text:
        print("\n[OK] Email chq@saverglass.com préservé dans clean_text")
    else:
        print("\n[ERREUR] Email chq@saverglass.com PAS trouvé dans clean_text !")

    if "font-family" in clean_text or "text-align" in clean_text:
        print("[ERREUR] Attributs HTML encore présents dans clean_text !")
    else:
        print("[OK] Pas d'attributs HTML dans clean_text")

    # 4. Appeler le matcher
    print("\n" + "="*60)
    print("APPEL MATCHER")
    print("="*60)
    matcher = get_email_matcher()
    await matcher.ensure_cache()

    print(f"Cache: {len(matcher._clients_cache)} clients, {len(matcher._items_cache)} produits")

    match_result = await matcher.match_email(
        body=clean_text,
        sender_email=email['from_address'],
        subject=email['subject']
    )

    print(f"\nRésultat matching:")
    print(f"  - Clients: {len(match_result.clients)}")
    for c in match_result.clients[:5]:
        print(f"    * {c.card_code}: {c.card_name} (score={c.score}, raison={c.match_reason})")

    print(f"  - Produits: {len(match_result.products)}")
    for p in match_result.products[:5]:
        print(f"    * {p.item_code}: {p.item_name or 'N/A'} (score={p.score})")

    print(f"  - Best client: {match_result.best_client.card_name if match_result.best_client else 'None'}")

    print("\n" + "="*60)
    if match_result.clients:
        print("[OK] Matching réussi !")
    else:
        print("[ERREUR] Aucun client trouvé !")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(test())
