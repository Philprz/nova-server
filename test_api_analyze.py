"""Test simulation exacte de l'API d'analyse"""
import asyncio
from services.email_matcher import get_email_matcher
from services.email_analyzer import get_email_analyzer

async def test_api_simulation():
    """Simule exactement ce que fait routes_graph.py"""

    # Données email SAVERGLASS
    subject = "demande de prix"
    from_address = "devis@rondot-poc.itspirit.ovh"  # Email reel recu
    body_text = """De : Quesnel, Christophe <chq@saverglass.com>
Objet : demande de prix

Bonjour Manu
Pourrais-tu me faire un devis pour l'article suivant
2323060165 qte : 1
Merci
--
 Christophe QUESNEL
MAGASINIER I.S.
Atelier I.S. Mecaniciens SGL
+33344464269"""

    print("="*60)
    print("TEST SIMULATION API ANALYZE - SAVERGLASS")
    print("="*60)
    print(f"Subject: {subject}")
    print(f"From: {from_address}")
    print(f"Body preview: {body_text[:100]}...")

    try:
        # Etape 1: Analyser avec email_analyzer
        print("\n--- Etape 1: Email Analyzer ---")
        analyzer = get_email_analyzer()
        analysis = await analyzer.analyze_email(
            subject=subject,
            body=body_text,
            sender_email=from_address,
            sender_name="Philippe PEREZ",
            pdf_contents=[]
        )
        print(f"Classification: {analysis.classification}")
        print(f"Is quote request: {analysis.is_quote_request}")
        print(f"Client name extracted: {analysis.extracted_data.client_name if analysis.extracted_data else 'None'}")

        # Etape 2: Nettoyer le texte (comme dans routes_graph.py)
        print("\n--- Etape 2: Clean HTML ---")
        clean_text = analyzer._clean_html(body_text)
        print(f"Clean text length: {len(clean_text)}")
        print(f"Clean text preview: {clean_text[:150]}...")

        # Etape 3: Matcher avec EmailMatcher
        print("\n--- Etape 3: Email Matcher ---")
        matcher = get_email_matcher()
        await matcher.ensure_cache()
        print(f"Cache loaded: {len(matcher._clients_cache)} clients, {len(matcher._items_cache)} items")

        # Appel EXACT comme dans routes_graph.py ligne 423-427
        match_result = await matcher.match_email(
            body=clean_text,
            sender_email=from_address,  # IMPORTANT: c'est from_address pas chq@saverglass.com
            subject=subject
        )

        print(f"\nMatch result:")
        print(f"  - Clients matches: {len(match_result.clients)}")
        for c in match_result.clients[:3]:
            print(f"    * {c.card_code}: {c.card_name} (score {c.score})")
        print(f"  - Products matches: {len(match_result.products)}")
        for p in match_result.products[:3]:
            print(f"    * {p.item_code}: {p.item_name} (score {p.score})")
        print(f"  - Best client: {match_result.best_client.card_name if match_result.best_client else 'None'}")

        # Etape 4: Verifier extracted_data enrichissement
        print("\n--- Etape 4: Enrichissement ---")
        if match_result.best_client:
            print(f"Client card code serait: {match_result.best_client.card_code}")
        if match_result.products:
            print(f"Produits seraient remplaces par: {[p.item_code for p in match_result.products]}")

    except Exception as e:
        print(f"\nERREUR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_api_simulation())
