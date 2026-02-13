"""Test avec un body_preview TRONQUÉ (simule le problème réel)"""
import asyncio
from services.email_analyzer import get_email_analyzer

async def test_truncated_preview():
    """
    Simule le cas où body_preview est tronqué à 255 caractères
    et ne contient PAS "demande de chiffrage".
    """

    subject = "Demande chiffrage MarmaraCam"

    # Body COMPLET (comme dans l'email réel)
    full_body = """Bonjour,

Veuillez trouver ci-joint notre demande de prix pour les références suivantes destinées à notre client Sheppee International.

Merci de nous faire parvenir votre meilleure offre dans les plus brefs délais.

Nous restons à votre disposition pour tout complément d'information.

--- INFORMATIONS COMPLÉMENTAIRES ---
Veuillez trouver ci-joint la demande de chiffrage pour des éléments Sheppee international. Please send the offer to our technical team.

Cordialement,
Philippe PEREZ
De : msezen@marmaracam.com.tr"""

    # Body PREVIEW TRONQUÉ (seulement les 255 premiers caractères)
    # Ne contient PAS "demande de chiffrage" car c'est plus loin dans le texte
    truncated_preview = full_body[:255]

    print("=" * 80)
    print("TEST BODY PREVIEW TRONQUÉ - SIMULATION DU PROBLÈME")
    print("=" * 80)
    print(f"Sujet: {subject}")
    print()
    print(f"Full body length: {len(full_body)} caracteres")
    print(f"Preview length: {len(truncated_preview)} caracteres")
    print()
    print("Preview contient 'demande de chiffrage':", "demande de chiffrage" in truncated_preview.lower())
    print("Full body contient 'demande de chiffrage':", "demande de chiffrage" in full_body.lower())
    print()

    analyzer = get_email_analyzer()

    # === TEST 1: Avec PREVIEW TRONQUÉ (problème) ===
    print("=" * 80)
    print("TEST 1: Analyse avec PREVIEW TRONQUÉ (255 chars)")
    print("=" * 80)
    print("Preview:")
    print("-" * 80)
    print(truncated_preview)
    print("-" * 80)
    print()

    quick_result_preview = analyzer.quick_classify(subject, truncated_preview)

    print(f"Score: {quick_result_preview['score']}")
    print(f"Likely quote: {quick_result_preview['likely_quote']}")
    print(f"Confidence: {quick_result_preview['confidence']}")
    print(f"Regles matchees:")
    for rule in quick_result_preview['matched_rules']:
        print(f"  [+] {rule}")
    print()

    if not quick_result_preview['likely_quote']:
        print("[PROBLEME] Avec preview tronque, l'email n'est PAS detecte!")
        print(f"Score {quick_result_preview['score']} < 15")
    else:
        print("[OK] Meme avec preview tronque, l'email est detecte (grâce au sujet)")

    print()

    # === TEST 2: Avec BODY COMPLET (solution) ===
    print("=" * 80)
    print("TEST 2: Analyse avec BODY COMPLET")
    print("=" * 80)

    quick_result_full = analyzer.quick_classify(subject, full_body)

    print(f"Score: {quick_result_full['score']}")
    print(f"Likely quote: {quick_result_full['likely_quote']}")
    print(f"Confidence: {quick_result_full['confidence']}")
    print(f"Regles matchees:")
    for rule in quick_result_full['matched_rules']:
        print(f"  [+] {rule}")
    print()

    if quick_result_full['likely_quote']:
        print("[OK] Avec body complet, l'email EST detecte!")
    else:
        print("[PROBLEME] Même avec body complet, l'email n'est pas detecte!")

    print()

    # === RÉSUMÉ ===
    print("=" * 80)
    print("RESUME")
    print("=" * 80)
    print(f"Preview tronque (255 chars): Score={quick_result_preview['score']} -> {'DETECTE' if quick_result_preview['likely_quote'] else 'NON DETECTE'}")
    print(f"Body complet ({len(full_body)} chars): Score={quick_result_full['score']} -> {'DETECTE' if quick_result_full['likely_quote'] else 'NON DETECTE'}")
    print()

    if quick_result_preview['likely_quote'] and quick_result_full['likely_quote']:
        print("[CONCLUSION] Le mot 'chiffrage' dans le SUJET suffit a detecter l'email")
        print("Le probleme n'est probablement PAS le body tronque dans ce cas.")
    elif not quick_result_preview['likely_quote'] and quick_result_full['likely_quote']:
        print("[CONCLUSION] Le body tronque EMPÊCHE la detection!")
        print("SOLUTION: Utiliser body_content (complet) au lieu de body_preview")
    else:
        print("[CONCLUSION] Probleme ailleurs (pas lie au truncation)")

    print()
    print("=" * 80)
    print("FIX APPLIQUÉ DANS routes_graph.py ligne 405-412")
    print("=" * 80)
    print("Le code verifie maintenant si body_content existe et n'est pas vide")
    print("avant d'utiliser body_preview.")
    print()
    print("PROCHAINE ÉTAPE:")
    print("  1. Redemarrer le backend")
    print("  2. Rafraichir la page (F5)")
    print("  3. Verifier les logs: 'Using full body_content' ou 'using body_preview'")
    print("  4. Si toujours 'using body_preview', le probleme est dans graph_service.py")

if __name__ == "__main__":
    asyncio.run(test_truncated_preview())
