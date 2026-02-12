"""
Test du matching intelligent avec le PDF réel Marmara Cam (28 produits)
Stratégie en cascade: Exact → Apprentissage → Fuzzy → Création
"""
import asyncio
from services.email_matcher import get_email_matcher

async def test_marmara_intelligent():
    matcher = get_email_matcher()
    await matcher.ensure_cache()

    # Contenu RÉEL du PDF Marmara Cam (28 produits)
    pdf_content = """
OFFER REQUEST FORM
Marmara Cam Sanayi ve Tic. A.Ş.
Sheppee International Ltd
Email: msezen@marmaracam.com.tr
Fax: +90 282 675 10 20
Date : 1.07.2025
Form No : 26576

Row 1: HST-117-03 - SIZE 3 PUSHER BLADE CARBON - SHEPPEE SIZE 3 TRANSFER TIRNAĞI KARBON - 50 Adet
Row 2: C233-50AT10-1940G3 - D5 SHEPPEE STAKER X EKSENİ & Y EKSENİ ZAMAN KAYIŞI - 50AT10/1940G3 CONTITECH GENERATION 3 SYNCHROFLEX - 2 Adet
Row 3: C281-RV80 - Z-AXIS GEAR UNIT - SHEPPEE CODE: C281-RV80 DRAWING: TRI-1104 POS.8 - 1 Adet
Row 4: C362-M035-SF - FLANGED BEARING UNIT - SHEPPEE CODE: C362-M035-SF DRAWING: TRI-1104 POS.9 - 2 Adet
Row 5: TRI-037 - LIFT ROLLER STUD - SHEPPEE CODE: TRI-037 DRAWING: TRI-1105 POS.1 - 2 Adet
Row 6: TRI-038 - LIFT ROLLER ECCENTRIC - SHEPPEE CODE: TRI-038 DRAWING: TRI-1105 POS.2 - 2 Adet
Row 7: TRI-066 - SUPPORT BLOCK - SHEPPEE CODE: TRI-066 DRAWING: TRI-1105 POS.4 - 2 Adet
Row 8: TRI-067 - LIFT ROLLER SPACER - SHEPPEE CODE: TRI-067 DRAWING: TRI-1105 POS.5 - 2 Adet
Row 9: TRI-075 - PIVOT PIN - SHEPPEE CODE: TRI-075 DRAWING: TRI-1105 POS.6 - 2 Adet
Row 10: P-0301L-SLT - VERTICAL CLAMP CARRIER - LH - SHEPPEE CODE: P-0301L-SLT DRAWING: TRI-1105 POS.8 - 1 Adet
Row 11: P-0301R-SLT - VERTICAL CLAMP CARRIER - RH - SHEPPEE CODE: P-0301R-SLT DRAWING: TRI-1105 POS.9 - 1 Adet
Row 12: C356-NUTD25 - CAM FOLLOWER - SHEPPEE CODE: C356-NUTD25 DRAWING: TRI-1105 POS.14 - 2 Adet
Row 13: TRI-051 - SHEPPEE TRI-FLEX X-AXIS & Y-AXIS GEAR UNIT CYCLO GEARBOX - SHEPPEE CODE: TRI-051 DRAWING NO. TRI-1106 - 2 Adet
Row 14: C421-MET-020 - M20 NUT - SHEPPEE CODE: C421-MET-020 DRAWING: TRI-1105 POS.19 - 2 Adet
Row 15: C431M-020 - M20 PLAIN WASHER - SHEPPEE CODE: C431M-020 DRAWING: TRI-1105 POS.22 - 2 Adet
Row 16: TRI-011 - BEARING RETAINER - SHEPPEE CODE: TRI-011 DRAWING: TRI-1106 POS.5 - 1 Adet
Row 17: TRI-014 - BELT CLAMP BOTTOM - SHEPPEE CODE: TRI-014 DRAWING: TRI-1106 POS.8 - 1 Adet
Row 18: TRI-015 - BELT CLAMP UPPER - SHEPPEE CODE: TRI-015 DRAWING: TRI-1106 POS.9 - 1 Adet
Row 19: TRI-016 - BELT CLAMP COUPLING - SHEPPEE CODE: TRI-016 DRAWING: TRI-1106 POS.10 - 1 Adet
Row 20: TRI-018 - DRIVE SCREW - SHEPPEE CODE: TRI-018 DRAWING: TRI-1106 POS.12 - 1 Adet
Row 21: C315-6305RS - BALL BEARING - SHEPPEE CODE: C315-6305RS DRAWING: TRI-1106 POS.17 - 2 Adet
Row 22: TRI-009 - DRIVE PULLEY 40T - SHEPPEE STAKER X&Y EKSENLERİ İÇİN KAYIŞ TAHRİK KASNAĞI - 1 Adet
Row 23: TRI-010 - IDLE PULLEY 40T - SHEPPEE STAKER X&Y EKSENLERİ İÇİN KAYIŞ AVARE KASNAĞI - 1 Adet
Row 24: C391-14-LM - LM GUIDE RAIL 1160 LG - D5 SHEPPEE STAKER X EKSENİ LİNEER HAREKET GAYTI - 2 Adet
Row 25: C391-15-LM - LM RAIL 1480 LG - D5 SHEPPEE STAKER Y EKSENİ LİNEER HAREKET GAYTI - 2 Adet
Row 26: C361-NP25-MS44 - BEARING PILLOW BLOCK - SHEPPEE CODE: C361-NP25-MS44 DRAWING: TRI-1103 POS.6 - 2 Adet
Row 27: TRI-036 - LIFT CAM - SHEPPEE CODE: TRI-036 DRAWING: TRI-1104 POS.1 - 2 Adet
Row 28: MRS-0005 - Z-AXIS DRIVE SHAFT - SHEPPEE CODE: MRS-0005 DRAWING: TRI-1104 POS.3 - 1 Adet
"""

    print("="*80)
    print("TEST MATCHING INTELLIGENT - PDF MARMARA CAM")
    print("28 produits SHEPPEE - Strategie en cascade")
    print("="*80)

    # Test du matching complet
    result = await matcher.match_email(
        body=pdf_content,
        sender_email="msezen@marmaracam.com.tr",
        subject="Offer Request Form No 26576"
    )

    # ===== CLIENT =====
    print("\n[1] CLIENT")
    print("-" * 80)
    if result.best_client:
        print(f"Client trouve: {result.best_client.card_name}")
        print(f"CardCode: {result.best_client.card_code}")
        print(f"Score: {result.best_client.score}")
        print(f"Methode: {result.best_client.match_reason}")
        client_code = result.best_client.card_code
    else:
        print("AUCUN CLIENT TROUVE")
        client_code = None

    # ===== PRODUITS =====
    print(f"\n[2] PRODUITS - {len(result.products)} produit(s) traite(s)")
    print("-" * 80)

    # Regrouper par statut
    exact_matches = [p for p in result.products if p.score == 100]
    fuzzy_matches = [p for p in result.products if 60 <= p.score < 100]
    not_found = [p for p in result.products if p.not_found_in_sap]

    print(f"\nExact Match SAP (score 100): {len(exact_matches)} produit(s)")
    for p in exact_matches[:5]:
        print(f"  - {p.item_code}: {p.item_name[:50]} (qte: {p.quantity})")
    if len(exact_matches) > 5:
        print(f"  ... et {len(exact_matches) - 5} autres")

    print(f"\nFuzzy Match SAP (score 60-99): {len(fuzzy_matches)} produit(s)")
    for p in fuzzy_matches[:5]:
        print(f"  - {p.item_code}: {p.item_name[:50]} (qte: {p.quantity}, score: {p.score})")
        print(f"    Raison: {p.match_reason}")
    if len(fuzzy_matches) > 5:
        print(f"  ... et {len(fuzzy_matches) - 5} autres")

    print(f"\nNON TROUVES dans SAP (a creer): {len(not_found)} produit(s)")
    for p in not_found:
        print(f"  - {p.item_code}: {p.item_name[:50]} (qte: {p.quantity})")
        print(f"    Statut: PENDING creation/validation")

    # ===== STATISTIQUES =====
    print(f"\n[3] STATISTIQUES")
    print("-" * 80)
    total_products = 28  # Attendu
    found_auto = len(exact_matches) + len([p for p in fuzzy_matches if p.score >= 85])
    found_validate = len([p for p in fuzzy_matches if 70 <= p.score < 85])
    to_create = len(not_found)

    print(f"Total produits demandes: {total_products}")
    print(f"Trouves automatiquement (score >= 85): {found_auto} ({found_auto/total_products*100:.1f}%)")
    print(f"Trouves avec validation (score 70-84): {found_validate} ({found_validate/total_products*100:.1f}%)")
    print(f"A creer dans SAP: {to_create} ({to_create/total_products*100:.1f}%)")

    # ===== APPRENTISSAGE =====
    print(f"\n[4] APPRENTISSAGE AUTOMATIQUE")
    print("-" * 80)

    # Verifier les mappings enregistres
    from services.product_mapping_db import get_product_mapping_db
    mapping_db = get_product_mapping_db()
    stats = mapping_db.get_statistics()

    print(f"Total mappings enregistres: {stats['total']}")
    print(f"  - Valides: {stats['validated']}")
    print(f"  - En attente: {stats['pending']}")
    print(f"  - Exact matches: {stats['exact_matches']}")
    print(f"  - Fuzzy matches: {stats['fuzzy_matches']}")
    print(f"  - Manuel: {stats['manual_matches']}")

    if stats['pending'] > 0:
        print(f"\n[!] {stats['pending']} produit(s) necessitent validation manuelle")
        pending = mapping_db.get_pending_mappings(limit=5)
        for p in pending:
            print(f"  - {p['external_code']}: {p['external_description'][:40]}")

    # ===== ACTIONS RECOMMANDEES =====
    print(f"\n[5] ACTIONS RECOMMANDEES")
    print("-" * 80)

    if to_create > 0:
        print(f"1. Valider {to_create} produit(s) non trouve(s):")
        print(f"   - Option A: Associer a des codes SAP existants")
        print(f"   - Option B: Creer dans SAP (POST /Items)")
        print(f"   - Dashboard: /validation/products")

    if found_validate > 0:
        print(f"2. Verifier {found_validate} produit(s) avec fuzzy match (score < 85)")
        print(f"   - Confirmer les correspondances trouvees")

    if found_auto >= total_products * 0.8:
        print(f"3. Taux de reussite: {found_auto/total_products*100:.1f}% - EXCELLENT!")
    else:
        print(f"3. Taux de reussite: {found_auto/total_products*100:.1f}% - Besoin d'apprentissage")

    print("\n" + "="*80)
    print("Test termine!")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(test_marmara_intelligent())
