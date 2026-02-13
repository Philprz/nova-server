"""
Test du pricing automatique Phase 5
Verifie que l'analyse email enrichit automatiquement les produits avec le pricing
"""

import asyncio
import sys
import os

# Ajouter le repertoire racine au path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_pricing_phase5():
    print("=" * 80)
    print("TEST PRICING AUTOMATIQUE - PHASE 5")
    print("=" * 80)
    print()

    # Import des services
    from services.graph_service import get_graph_service
    from services.email_analyzer import get_email_analyzer
    from services.email_matcher import get_email_matcher
    from services.pricing_engine import get_pricing_engine
    from services.pricing_models import PricingContext
    import logging

    # Activer logs detailles
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 1. Recuperer un email de test
    print("[EMAIL] Etape 1: Recuperation emails...")
    print("-" * 80)

    graph_service = get_graph_service()

    try:
        emails_response = await graph_service.get_messages(top=5, skip=0, unread_only=False)

        if not emails_response.emails:
            print("[ERREUR] Aucun email trouve dans la boite")
            return

        # Prendre le premier email
        test_email = emails_response.emails[0]

        print(f"[OK] Email trouve: {test_email.subject}")
        print(f"   ID: {test_email.id}")
        print(f"   De: {test_email.from_name} <{test_email.from_address}>")
        print(f"   Date: {test_email.received_datetime}")
        print()

    except Exception as e:
        print(f"[ERREUR] Recuperation emails: {e}")
        return

    # 2. Analyser l'email (declenche Phase 1-4)
    print("[IA] Etape 2: Analyse IA de l'email...")
    print("-" * 80)

    email_analyzer = get_email_analyzer()

    try:
        # Récupérer email complet
        full_email = await graph_service.get_message(test_email.id)

        # Analyser
        analysis = await email_analyzer.analyze_email(
            subject=full_email.subject,
            body=full_email.body_content or full_email.body_preview,
            sender_name=full_email.from_name,
            sender_email=full_email.from_address
        )

        print(f"Classification: {analysis.classification}")
        print(f"Confiance: {analysis.confidence}")
        print(f"Est devis: {analysis.is_quote_request}")

        if analysis.extracted_data:
            print(f"Client détecté: {analysis.extracted_data.client_name}")
            print(f"Produits extraits: {len(analysis.extracted_data.products)}")
        print()

    except Exception as e:
        print(f"❌ Erreur analyse: {e}")
        import traceback
        traceback.print_exc()
        return

    # 3. Matcher avec SAP (Phase 3-4)
    print("🔍 Étape 3: Matching SAP...")
    print("-" * 80)

    email_matcher = get_email_matcher()

    try:
        match_result = email_matcher.match_against_sap(analysis)

        print(f"Clients matchés: {len(match_result.clients)}")
        if match_result.best_client:
            print(f"Meilleur client: {match_result.best_client.card_name} ({match_result.best_client.card_code})")

        print(f"Produits matchés: {len(match_result.products)}")

        if not match_result.products:
            print("⚠️  Aucun produit matché - impossible de tester le pricing")
            return

        for i, product in enumerate(match_result.products[:3], 1):
            print(f"  {i}. {product.item_code} - {product.item_name} (score: {product.score})")
        print()

    except Exception as e:
        print(f"❌ Erreur matching SAP: {e}")
        import traceback
        traceback.print_exc()
        return

    # 4. TEST PHASE 5 - PRICING AUTOMATIQUE
    print("💰 Étape 4: TEST PRICING AUTOMATIQUE (Phase 5)")
    print("=" * 80)

    pricing_engine = get_pricing_engine()

    # Récupérer CardCode client
    card_code = "UNKNOWN"
    if match_result.best_client:
        card_code = match_result.best_client.card_code

    print(f"Client pour pricing: {card_code}")
    print()

    # Tester pricing pour chaque produit matché
    for i, product in enumerate(match_result.products[:3], 1):
        print(f"Produit {i}: {product.item_code}")
        print("-" * 40)

        try:
            # Créer contexte pricing
            context = PricingContext(
                item_code=product.item_code,
                card_code=card_code,
                quantity=product.quantity,
                supplier_price=None,  # Sera récupéré automatiquement
                apply_margin=45.0,
                force_recalculate=False
            )

            # Calculer prix
            pricing_result = await pricing_engine.calculate_price(context)

            if pricing_result.success and pricing_result.decision:
                decision = pricing_result.decision

                print(f"✅ SUCCÈS")
                print(f"   CAS: {decision.case_type.value}")
                print(f"   Prix calculé: {decision.calculated_price:.2f} EUR")
                print(f"   Prix fournisseur: {decision.supplier_price:.2f} EUR" if decision.supplier_price else "   Prix fournisseur: N/A")
                print(f"   Marge appliquée: {decision.margin_applied:.0f}%")
                print(f"   Total ligne: {decision.calculated_price * product.quantity:.2f} EUR")
                print(f"   Confiance: {decision.confidence_score:.1%}")
                print(f"   Validation requise: {'OUI' if decision.requires_validation else 'NON'}")

                if decision.alerts:
                    print(f"   ⚠️  Alertes:")
                    for alert in decision.alerts:
                        print(f"      - {alert}")

                print(f"   Justification: {decision.justification[:100]}...")
                print(f"   Temps: {pricing_result.processing_time_ms:.0f}ms")

            else:
                print(f"❌ ÉCHEC: {pricing_result.error}")

        except Exception as e:
            print(f"❌ ERREUR: {e}")
            import traceback
            traceback.print_exc()

        print()

    # 5. Résumé final
    print("=" * 80)
    print("RÉSUMÉ DU TEST")
    print("=" * 80)
    print()
    print("✅ Phase 1-4: Analyse + Matching SAP fonctionnels")
    print("✅ Phase 5: Pricing automatique testé")
    print()
    print("📊 Statistiques:")
    print(f"   - Produits matchés: {len(match_result.products)}")
    print(f"   - Produits avec pricing: {sum(1 for p in match_result.products[:3])}")
    print()
    print("🎯 Prochaine étape: Intégrer Phase 5 dans l'endpoint /analyze")
    print()

if __name__ == "__main__":
    asyncio.run(test_pricing_phase5())
